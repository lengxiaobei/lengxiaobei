"""Simple local agent discovery and invocation.

This module is intentionally thin: lengxiaobei should know how to find local
agents and hand work to them, without importing every agent framework directly.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.agents.integrations import build_reference_integrations


MARKER_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "SOUL.md",
    "BOOTSTRAP.md",
    "IDENTITY.md",
)


@dataclass
class LocalAgent:
    id: str
    name: str
    root: str
    markers: list[str] = field(default_factory=list)
    description: str = ""
    command: list[str] = field(default_factory=list)
    source: str = "discovered"

    def public_dict(self, include_command: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_command:
            data.pop("command", None)
        else:
            import logging
            logging.warning("Exposing agent command in public dict. Ensure this is intended for trusted consumers.")
        data["callable"] = self.source == "integrated" or bool(self.command)
        return data


class LocalAgentHub:
    """Discover and call locally installed agents via a small adapter contract."""

    def __init__(
        self,
        roots: list[Path] | None = None,
        config_path: Path | None = None,
        home: Path | None = None,
        max_depth: int = 4,
    ) -> None:
        self.home = home or Path.home()
        self.roots = roots or self._default_roots()
        self.config_path = config_path or self.home / ".lengxiaobei" / "local_agents.json"
        self.task_dir = self.config_path.parent / "agent_tasks"
        try:
            self.task_dir.mkdir(parents=True, exist_ok=True)  # Ensure task directory exists
        except OSError as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not create task directory {self.task_dir}: {e}", exc_info=True)
        self.max_depth = max_depth
        self.integrations = build_reference_integrations(home=self.home)

    def list_agents(self, refresh: bool = True) -> list[dict[str, Any]]:
        agents = self._load_agents(refresh=refresh)
        result = []
        for agent in agents:
            try:
                result.append(agent.public_dict())
            except Exception as e:
                # 记录错误但继续处理其他 agent
                result.append({
                    "id": getattr(agent, 'id', 'unknown'),
                    "name": getattr(agent, 'name', 'unknown'),
                    "error": str(e),
                    "callable": False,
                })
        return result

    def list_controlled_agents(self) -> list[dict[str, Any]]:
        agents: list[dict[str, Any]] = []
        for integration in self.integrations.values():
            status = self._integration_status(integration)
            profile = dict(status.get("profile") or integration.profile().as_dict())
            profile["kind"] = self._integration_kind(profile.get("id", ""))
            profile["name"] = self._native_lane_name(profile.get("id", ""), profile.get("name", ""))
            profile["description"] = self._native_lane_description(profile.get("id", ""), profile.get("description", ""))
            profile["callable"] = bool(status.get("ok"))
            profile["installed"] = bool(status.get("installed", status.get("ok")))
            profile["health"] = self._public_health(status)
            agents.append(profile)
        return agents

    def controlled_status(self, target: str = "all") -> dict[str, Any]:
        integration = self._integration(target)
        if integration:
            return self._integration_status(integration)
        return {"ok": True, "items": {name: self._integration_status(item) for name, item in self.integrations.items()}}

    def describe_agent(self, agent_id: str) -> dict[str, Any]:
        agent = self._find(agent_id) or self._controlled_agent(agent_id)
        if not agent:
            return {"ok": False, "error": f"local agent not found: {agent_id}"}
        return {"ok": True, "agent": agent.public_dict(include_command=True)}

    def run_agent(self, agent_id: str, prompt: str, timeout: int = 120, execute: bool = True) -> dict[str, Any]:
        integration = self._integration(agent_id)
        if integration:
            if not execute:
                return self._write_task(
                    agent=self._controlled_agent(agent_id),
                    prompt=prompt,
                    mode="queued",
                )
            result = integration.assign_task(prompt, timeout=timeout)
            if inspect.isawaitable(result):
                return self._run_awaitable_in_thread(result)
            return result
        agent = self._find(agent_id) or self._controlled_agent(agent_id)
        if not agent:
            return {"ok": False, "error": f"local agent not found: {agent_id}"}
        if not execute:
            return self._write_task(agent=agent, prompt=prompt, mode="queued")
        if not agent.command:
            return self._write_task(agent=agent, prompt=prompt, mode="inbox")

        command = [part.replace("{prompt}", prompt) for part in agent.command]
        if not any("{prompt}" in part for part in agent.command):
            command.append(prompt)
        proc = subprocess.run(
            command,
            cwd=agent.root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "agent": agent.public_dict(),
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    def assign_task(
        self,
        task: str,
        target: str = "auto",
        context: str = "",
        timeout: int = 300,
        execute: bool = True,
    ) -> dict[str, Any]:
        agent = self._select_controlled_agent(target=target, task=task)
        prompt = self._task_prompt(task=task, context=context, agent=agent)
        integration = self._integration(agent.id)
        result = (
            integration.assign_task(task=task, context=context, timeout=timeout)
            if integration and execute
            else self.run_agent(agent.id, prompt, timeout=timeout, execute=execute)
        )
        if inspect.isawaitable(result):
            result = self._run_awaitable_in_thread(result)
        assignment = self._write_task(
            agent=agent,
            prompt=prompt,
            mode="integrated" if integration and execute else "executed" if execute and agent.command else "queued",
            result=result,
        )
        return {
            "ok": result.get("ok", False),
            "target": agent.public_dict(),
            "assignment": assignment,
            "result": result,
        }

    def task_status(self, limit: int = 20) -> dict[str, Any]:
        if not self.task_dir.exists():
            return {"ok": True, "tasks": []}
        tasks: list[dict[str, Any]] = []
        for path in sorted(self.task_dir.glob("*.json"), reverse=True)[:limit]:
            try:
                tasks.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return {"ok": True, "tasks": tasks}

    def _load_agents(self, refresh: bool = True) -> list[LocalAgent]:
        del refresh  # kept for API clarity; discovery is cheap enough for now.
        agents: dict[str, LocalAgent] = {}
        for agent in self._controlled_agents():
            agents[agent.id] = agent
        for agent in self._load_configured_agents():
            agents[agent.id] = agent
        for agent in self._discover_agents():
            agents.setdefault(agent.id, agent)
        return sorted(agents.values(), key=lambda item: (item.source, item.name.lower(), item.root))

    def _controlled_agents(self) -> list[LocalAgent]:
        return [self._agent_from_integration(item) for item in self.integrations.values()]

    def _controlled_agent(self, agent_id: str) -> LocalAgent | None:
        normalized = agent_id.strip().lower()
        aliases = {
            "claw": "openclaw",
            "open-claw": "openclaw",
            "hermes-agent": "hermes",
            "open-human": "openhuman",
        }
        normalized = aliases.get(normalized, normalized)
        for agent in self._controlled_agents():
            if agent.id == normalized or agent.name.lower() == normalized:
                return agent
        return None

    def _integration(self, target: str):
        normalized = target.strip().lower()
        aliases = {
            "claw": "openclaw",
            "open-claw": "openclaw",
            "hermes-agent": "hermes",
            "open-human": "openhuman",
        }
        return self.integrations.get(aliases.get(normalized, normalized))

    def _agent_from_integration(self, integration: Any) -> LocalAgent:
        profile = integration.profile()
        root = self._integration_root(profile.id)
        return LocalAgent(
            id=profile.id,
            name=self._native_lane_name(profile.id, profile.name),
            root=str(root),
            markers=self._markers_for(root),
            description=self._native_lane_description(profile.id, profile.description),
            command=[],
            source="integrated",
        )

    def _native_lane_name(self, agent_id: str, fallback: str) -> str:
        names = {
            "openclaw": "通道运行时",
            "hermes": "反思技能核",
            "openhuman": "记忆连续性",
        }
        return names.get(agent_id, fallback)

    def _native_lane_description(self, agent_id: str, fallback: str) -> str:
        descriptions = {
            "openclaw": "冷小北原生通道、网关、插件和工具巡检能力线。",
            "hermes": "冷小北原生反思、技能生成、验证和评估能力线。",
            "openhuman": "冷小北原生画像、长期记忆、同步资料和上下文连续性能力线。",
        }
        return descriptions.get(agent_id, fallback)

    def _integration_root(self, agent_id: str) -> Path:
        roots = {
            "openclaw": self.home / ".openclaw",
            "hermes": self.home / ".hermes",
            "openhuman": self.home / ".openhuman",
        }
        return roots.get(agent_id, self.home)

    def _integration_kind(self, agent_id: str) -> str:
        kinds = {
            "openclaw": "gateway",
            "hermes": "orchestrator",
            "openhuman": "memory",
        }
        return kinds.get(agent_id, "agent")

    def _public_health(self, status: dict[str, Any]) -> dict[str, Any]:
        health = {
            "ok": bool(status.get("ok")),
            "installed": bool(status.get("installed", status.get("ok"))),
        }
        if "gateway_online" in status:
            health["gateway_online"] = bool(status.get("gateway_online"))
        if "gateway_compatible" in status:
            health["gateway_compatible"] = bool(status.get("gateway_compatible"))
        if "owner_alive" in status:
            health["owner_alive"] = bool(status.get("owner_alive"))
        gateway = status.get("gateway") or {}
        if isinstance(gateway, dict) and gateway.get("port"):
            health["port"] = gateway.get("port")
        if status.get("error"):
            health["error"] = str(status.get("error"))
        return health

    def _integration_status(self, integration: Any) -> dict[str, Any]:
        status = integration.status()
        if not inspect.isawaitable(status):
            return status or {}
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(status)
        return self._run_awaitable_in_thread(status)

    def _run_awaitable_in_thread(self, awaitable: Any) -> dict[str, Any]:
        result: dict[str, Any] = {}
        error: BaseException | None = None

        def runner() -> None:
            nonlocal result, error
            try:
                result = asyncio.run(awaitable) or {}
            except BaseException as exc:  # pragma: no cover - defensive thread bridge
                error = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout=8)
        if thread.is_alive():
            return {"ok": False, "installed": False, "error": "status check timed out"}
        if error:
            return {"ok": False, "installed": False, "error": str(error)}
        return result

    def _select_controlled_agent(self, target: str, task: str) -> LocalAgent:
        requested = self._controlled_agent(target)
        if requested:
            return requested
        normalized = task.lower()
        if any(word in normalized for word in ("channel", "gateway", "slack", "telegram", "whatsapp", "plugin", "device", "tool")):
            return self._controlled_agent("openclaw")
        if any(word in normalized for word in ("skill", "reflect", "evaluate", "trajectory", "hermes", "self-improve")):
            return self._controlled_agent("hermes")
        if any(word in normalized for word in ("memory", "profile", "sync", "openhuman", "personal data", "knowledge")):
            return self._controlled_agent("openhuman")
        return self._controlled_agent("openclaw")

    def _task_prompt(self, task: str, context: str, agent: LocalAgent) -> str:
        parts = [
            f"You are being controlled by lengxiaobei as the downstream {agent.name} agent.",
            "Complete the assigned task and return a concise result with actions taken, files changed, and blockers.",
            f"Task: {task}",
        ]
        if context:
            parts.append(f"Context: {context}")
        return "\n\n".join(parts)

    def _write_task(
        self,
        agent: LocalAgent,
        prompt: str,
        mode: str,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.task_dir.mkdir(parents=True, exist_ok=True)
        task_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
        payload = {
            "id": task_id,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "mode": mode,
            "prompt": prompt,
            "result": result,
            "created_at": time.time(),
        }
        path = self.task_dir / f"{task_id}-{agent.id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if not agent.command:
            inbox = Path(agent.root).expanduser() / "lengxiaobei_inbox"
            try:
                inbox.mkdir(parents=True, exist_ok=True)
                (inbox / f"{task_id}.md").write_text(prompt + "\n", encoding="utf-8")
                payload["inbox_path"] = str(inbox / f"{task_id}.md")
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as exc:
                payload["inbox_error"] = str(exc)
        return {"ok": True, "task_id": task_id, "path": str(path), **({"inbox_path": payload["inbox_path"]} if "inbox_path" in payload else {})}

    def _first_existing(self, paths: list[Path]) -> Path:
        for path in paths:
            expanded = Path(path).expanduser()
            if expanded.exists():
                return expanded.resolve()
        return Path(paths[0]).expanduser()

    def _command_if_exists(self, candidates: list[Path | str], args: list[str]) -> list[str]:
        for candidate in candidates:
            value = str(Path(candidate).expanduser()) if isinstance(candidate, Path) else candidate
            if "/" in value:
                if Path(value).exists():
                    return [value, *args]
            else:
                from shutil import which

                resolved = which(value)
                if resolved:
                    return [resolved, *args]
        return []

    def _load_configured_agents(self) -> list[LocalAgent]:
        if not self.config_path.exists():
            return []
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        entries = raw.get("agents", raw) if isinstance(raw, dict) else raw
        agents: list[LocalAgent] = []
        for item in entries or []:
            if not isinstance(item, dict):
                continue
            root = Path(os.path.expanduser(str(item.get("root") or self.home))).resolve()
            name = str(item.get("name") or root.name or "local-agent")
            agent_id = str(item.get("id") or self._slug(name, root))
            markers = self._markers_for(root)
            agents.append(
                LocalAgent(
                    id=agent_id,
                    name=name,
                    root=str(root),
                    markers=markers,
                    description=str(item.get("description") or self._description_from_markers(root, markers)),
                    command=[str(part) for part in item.get("command") or []],
                    source="configured",
                )
            )
        return agents

    def _discover_agents(self) -> list[LocalAgent]:
        agents: list[LocalAgent] = []
        seen_roots: set[Path] = set()
        for base in self.roots:
            base = Path(os.path.expanduser(str(base))).resolve()
            if not base.exists():
                continue
            for marker in self._walk_markers(base):
                root = marker.parent.resolve()
                if root in seen_roots:
                    continue
                seen_roots.add(root)
                markers = self._markers_for(root)
                name = self._name_for(root, markers)
                agents.append(
                    LocalAgent(
                        id=self._slug(name, root),
                        name=name,
                        root=str(root),
                        markers=markers,
                        description=self._description_from_markers(root, markers),
                    )
                )
        return agents

    def _walk_markers(self, base: Path) -> list[Path]:
        if any((base / marker).exists() for marker in MARKER_FILES):
            return [base / marker for marker in MARKER_FILES if (base / marker).exists()]
        results: list[Path] = []
        stack: list[tuple[Path, int]] = [(base, 0)]
        while stack:
            current, depth = stack.pop()
            if depth > self.max_depth:
                continue
            try:
                children = list(current.iterdir())
            except OSError:
                continue
            for child in children:
                if child.name.startswith(".") and child != base:
                    continue
                if child.is_file() and child.name in MARKER_FILES:
                    results.append(child)
                elif child.is_dir() and depth < self.max_depth:
                    stack.append((child, depth + 1))
        return results

    def _markers_for(self, root: Path) -> list[str]:
        return [marker for marker in MARKER_FILES if (root / marker).exists()]

    def _description_from_markers(self, root: Path, markers: list[str]) -> str:
        for marker in markers:
            path = root / marker
            try:
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    stripped = line.strip(" #\t")
                    if stripped:
                        return stripped[:180]
            except OSError:
                continue
        return ""

    def _find(self, agent_id: str) -> LocalAgent | None:
        normalized = agent_id.strip().lower()
        for agent in self._load_agents(refresh=True):
            if agent.id.lower() == normalized or agent.name.lower() == normalized:
                return agent
        return None

    def _name_for(self, root: Path, markers: list[str]) -> str:
        for marker in markers:
            path = root / marker
            try:
                title = next(
                    (
                        line.strip(" #\t")
                        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
                        if line.strip(" #\t")
                    ),
                    "",
                )
            except OSError:
                title = ""
            if title:
                return title[:80]
        return root.name or "local-agent"

    def _slug(self, name: str, root: Path) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "agent"
        suffix = re.sub(r"[^a-z0-9]+", "-", root.name.lower()).strip("-") or "local"
        return f"{base}-{suffix}"[:96]

    def _default_roots(self) -> list[Path]:
        return [
            self.home / ".codex",
            self.home / ".openclaw",
            self.home / ".hermes",
            self.home / "openclaw",
            self.home / "hermes-agent",
            self.home / "projects",
        ]
