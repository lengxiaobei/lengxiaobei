"""Reflection engine boundary.

参考来源：Hermes 的 Nudge/reflector：从最近执行轨迹中发现可复用模式，写入记忆，
必要时生成 pending 技能草稿等待人工审核。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.evolution.skill_gen import draft_from_trace


class Reflector:
    """反思器：把运行轨迹转成记忆或技能候选。"""

    def __init__(self, project_root: Path, memory: Any, logger: Any, dispatcher: Any | None = None, skill_store: Any | None = None):
        self.project_root = project_root
        self.memory = memory
        self.logger = logger
        self.dispatcher = dispatcher
        self.skill_store = skill_store
        self.last_reflection: dict[str, Any] | None = None

    def reflect(self, topic: str = "system", force_skill: bool = True) -> dict[str, Any]:
        """记录一次反思，并在有成功轨迹时生成技能草稿。"""
        trace = self.dispatcher.recent_traces(limit=20) if self.dispatcher else []
        successful = [item for item in trace if item.get("ok")]
        content = f"reflection requested: {topic}; trace_count={len(trace)}; successful={len(successful)}"
        node = self.memory.add_node(content=content, node_type="reflection", metadata={"topic": topic, "reference_agent": "Hermes"})
        skill = None
        if successful and self.skill_store and force_skill:
            skill = draft_from_trace(name=f"auto_{node['id'][:8]}", trigger=topic, trace=successful[:8])
            self.skill_store.save(skill)
        self.last_reflection = {"status": "recorded", "node_id": node["id"], "draft_skill": skill, "trace_count": len(trace)}
        return self.last_reflection

    def stats(self) -> dict[str, Any]:
        traces = self.dispatcher.recent_traces(limit=200) if self.dispatcher else []
        ok = sum(1 for item in traces if item.get("ok"))
        return {"trace_count": len(traces), "success_count": ok, "fail_count": len(traces) - ok, "last_reflection": self.last_reflection}
