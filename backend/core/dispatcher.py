"""Tool dispatcher with a clear governance boundary.

参考来源：
- OpenClaw：Commander 只产出意图和工具名，Dispatcher 统一执行工具并返回 observation。
- Hermes：每次工具执行都保留成功/失败轨迹，后续可用于技能提炼和反思。
"""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolObservation:
    """工具执行结果，参考 OpenClaw observation schema 与 Hermes trace。"""

    ok: bool
    tool: str
    result: Any = None
    error: str | None = None
    elapsed_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "tool": self.tool, "result": self.result, "error": self.error, "elapsed_ms": self.elapsed_ms}


class Dispatcher:
    """集中式工具调度器，落地 OpenClaw 工具执行和 Hermes 轨迹记录。"""

    def __init__(self, tools: Any, logger: Any, sqlite: Any | None = None):
        self.tools = tools
        self.logger = logger
        self.sqlite = sqlite
        self.trace: list[dict[str, Any]] = []

    async def dispatch(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        started = time.perf_counter()
        tool = self.tools.get(name)
        if tool is None:
            observation = ToolObservation(False, name, error=f"unknown tool: {name}")
            self._record(observation, args)
            return observation.as_dict()
        try:
            result = tool(**args)
            if inspect.isawaitable(result):
                result = await result
            observation = ToolObservation(True, name, result=result, elapsed_ms=round((time.perf_counter() - started) * 1000, 3))
        except Exception as exc:
            self.logger.exception("tool failed: %s", name)
            observation = ToolObservation(False, name, error=str(exc), elapsed_ms=round((time.perf_counter() - started) * 1000, 3))
        self._record(observation, args)
        return observation.as_dict()

    def recent_traces(self, limit: int = 50) -> list[dict[str, Any]]:
        if self.sqlite:
            return self.sqlite.list_tool_traces(limit=limit)
        return list(reversed(self.trace[-limit:]))

    def _record(self, observation: ToolObservation, args: dict[str, Any]) -> None:
        """保留最近执行轨迹，供 Hermes 风格反思器提炼技能。"""
        trace = {"args": args, **observation.as_dict()}
        self.trace.append(trace)
        del self.trace[:-200]
        if self.sqlite:
            self.sqlite.record_tool_trace(trace)
