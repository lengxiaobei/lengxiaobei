"""Autonomous project execution primitives."""

from __future__ import annotations

import time
from typing import Any


class AutonomyExecutor:
    """Use Dispatcher tools to inspect, edit, and verify the project."""

    def __init__(self, dispatcher: Any):
        self.dispatcher = dispatcher

    async def run_checks(self, include_expensive: bool = False) -> dict[str, Any]:
        commands = [["python3", "-m", "compileall", "-q", "backend"]]
        if include_expensive:
            commands.append(["pytest", "backend/tests", "-q"])
        checks = []
        for command in commands:
            result = await self.dispatcher.dispatch("shell_exec", {"command": command, "timeout": 120})
            checks.append({"command": command, "result": result})
        ok = all(item["result"].get("ok") and item["result"].get("result", {}).get("returncode") == 0 for item in checks)
        return {"ok": ok, "checks": checks, "expensive": include_expensive, "ts": time.time()}

    async def write_roadmap(self, content: str) -> dict[str, Any]:
        return await self.dispatcher.dispatch(
            "filesystem_write",
            {"path": "data/autonomy/roadmap.md", "content": content, "create_parents": True},
        )

    async def append_changelog(self, content: str) -> dict[str, Any]:
        return await self.dispatcher.dispatch(
            "filesystem_append",
            {"path": "data/autonomy/changelog.md", "content": content, "create_parents": True},
        )

