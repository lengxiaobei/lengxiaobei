"""Canonical tool registry for the YourAgent backend.

参考来源：OpenClaw 的工具生态：内置工具、动态技能和外部能力都通过 registry 暴露，
Commander/Dispatcher 不直接 import 具体工具。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from backend.tools.builtin import browser, filesystem, web
from backend.tools.builtin.shell import run_readonly


class ToolRegistry:
    """统一工具注册表，落地 OpenClaw 风格工具生态。"""

    def __init__(
        self,
        project_root: Path,
        memory: Any | None = None,
        reflector: Any | None = None,
        skill_store: Any | None = None,
        vector_store: Any | None = None,
    ):
        self.project_root = Path(project_root)
        self.memory = memory
        self.reflector = reflector
        self.skill_store = skill_store
        self.vector_store = vector_store
        self._tools: dict[str, Callable[..., Any]] = {}
        self.register("system_status", self._system_status)
        self.register("memory_search", self._memory_search)
        self.register("memory_reindex", self._memory_reindex)
        self.register("reflect", self._reflect)
        self.register("skill_list", self._skill_list)
        self.register("skill_execute", self._skill_execute)
        self.register("filesystem_read", self._filesystem_read)
        self.register("shell_readonly", self._shell_readonly)
        self.register("web_fetch", web.fetch)
        self.register("browser", browser.unavailable)
        self.register("browser_fetch_text", browser.fetch_text)
        self.register("browser_screenshot", browser.screenshot)

    def bind(
        self,
        *,
        memory: Any | None = None,
        reflector: Any | None = None,
        skill_store: Any | None = None,
        vector_store: Any | None = None,
    ) -> None:
        self.memory = memory or self.memory
        self.reflector = reflector or self.reflector
        self.skill_store = skill_store or self.skill_store
        self.vector_store = vector_store or self.vector_store

    def register(self, name: str, func: Callable[..., Any]) -> None:
        self._tools[name] = func

    def get(self, name: str) -> Callable[..., Any] | None:
        return self._tools.get(name)

    def list(self) -> list[str]:
        return sorted(self._tools)

    def describe(self) -> list[dict[str, str]]:
        return [{"name": name, "callable": getattr(func, "__name__", repr(func))} for name, func in sorted(self._tools.items())]

    def _system_status(self) -> dict[str, Any]:
        return {"project_root": str(self.project_root), "time": time.time(), "tools": self.list()}

    def _memory_search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if self.vector_store:
            return self.vector_store.search(query, limit=limit)
        return self.memory.search(query, limit=limit) if self.memory else []

    def _memory_reindex(self, limit: int = 1000) -> dict[str, Any]:
        return self.vector_store.reindex(limit=limit) if self.vector_store else {"status": "unavailable"}

    def _reflect(self, topic: str = "system") -> dict[str, Any]:
        return self.reflector.reflect(topic) if self.reflector else {"status": "unavailable"}

    def _skill_list(self) -> list[dict[str, Any]]:
        return self.skill_store.list() if self.skill_store else []

    def _skill_execute(self, name: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        """执行 approved 技能的声明式步骤，局部参考 Hermes 技能运行器。"""
        if not self.skill_store:
            return {"ok": False, "error": "skill store unavailable"}
        skill = self.skill_store.load(name)
        if not skill:
            return {"ok": False, "error": f"skill not found: {name}"}
        if skill.get("status") != "approved":
            return {"ok": False, "error": "skill is not approved"}
        results: list[Any] = []
        ok = True
        for step in skill.get("steps") or []:
            if isinstance(step, dict) and step.get("tool"):
                tool = self.get(str(step["tool"]))
                if not tool:
                    ok = False
                    results.append({"ok": False, "error": f"unknown tool {step['tool']}"})
                    continue
                args = dict(step.get("args") or {})
                if step.get("merge_inputs"):
                    args.update(inputs or {})
                try:
                    results.append({"ok": True, "tool": step["tool"], "result": tool(**args)})
                except Exception as exc:
                    ok = False
                    results.append({"ok": False, "tool": step["tool"], "error": str(exc)})
            else:
                results.append({"ok": True, "instruction": str(step)})
        self.skill_store.record_result(name, ok)
        return {"ok": ok, "skill": name, "results": results}

    def _filesystem_read(self, path: str, limit: int = 12000) -> str:
        return filesystem.read_text(path=path, root=self.project_root, limit=limit)

    def _shell_readonly(self, command: list[str], timeout: int = 30) -> dict[str, Any]:
        return run_readonly(command=command, cwd=self.project_root, timeout=timeout)
