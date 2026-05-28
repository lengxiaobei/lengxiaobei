"""Simple local agent discovery and invocation."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

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

    def describe_agent(self, agent_id: str) -> dict[str, Any]:
        agent = self._find(agent_id)
        if not agent:
            return {"ok": False, "error": f"local agent not found: {agent_id}"}
        return {"ok": True, "agent": agent.public_dict(include_command=True)}

    def run_agent(self, agent_id: str, prompt: str, timeout: int = 120, execute: bool = True) -> dict[str, Any]:
        agent = self._find(agent_id)
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
        for agent in self._load_configured_agents():
            agents[agent.id] = agent
        for agent in self._discover_agents():
            agents.setdefault(agent.id, agent)
        return sorted(agents.values(), key=lambda item: (item.source, item.name.lower(), item.root))

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
        ]
