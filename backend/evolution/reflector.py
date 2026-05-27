"""Reflection engine boundary.

参考来源：Hermes 的 Nudge/reflector：从最近执行轨迹中发现可复用模式，写入记忆，
必要时生成 pending 技能草稿等待人工审核。
"""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from backend.evolution.skill_gen import draft_from_trace


class Reflector:
    """反思器：把运行轨迹转成记忆或技能候选。"""

    def __init__(
        self,
        project_root: Path,
        memory: Any,
        logger: Any,
        dispatcher: Any | None = None,
        skill_store: Any | None = None,
        dedupe_window_seconds: int = 7 * 24 * 60 * 60,
    ):
        self.project_root = project_root
        self.memory = memory
        self.logger = logger
        self.dispatcher = dispatcher
        self.skill_store = skill_store
        self.dedupe_window_seconds = dedupe_window_seconds
        self.last_reflection: dict[str, Any] | None = None

    def reflect(self, topic: str = "system", force_skill: bool = True) -> dict[str, Any]:
        """记录一次反思，并在有新成功轨迹时生成 pending 技能草稿。"""
        trace = self.dispatcher.recent_traces(limit=20) if self.dispatcher else []
        last_cutoff = self._last_skill_trace_cutoff(topic)
        successful = [item for item in trace if item.get("ok") and self._trace_ts(item) > last_cutoff]
        content = (
            f"reflection requested: {topic}; trace_count={len(trace)}; "
            f"new_successful={len(successful)}; last_cutoff={last_cutoff}"
        )
        node = self.memory.add_node(content=content, node_type="reflection", metadata={"topic": topic, "reference_agent": "Hermes"})
        skill = None
        skipped_reason = None
        if not force_skill:
            skipped_reason = "force_skill_false"
        elif not successful:
            skipped_reason = "no_new_successful_trace"
        elif self._has_recent_trigger(topic):
            skipped_reason = "duplicate_trigger_within_7_days"
        elif self.skill_store:
            skill = draft_from_trace(name=f"auto_{node['id'][:8]}", trigger=topic, trace=successful[:8])
            self.skill_store.save(skill)
        else:
            skipped_reason = "skill_store_unavailable"
        self.last_reflection = {
            "status": "recorded",
            "node_id": node["id"],
            "draft_skill": skill,
            "skipped_reason": skipped_reason,
            "trace_count": len(trace),
            "new_successful_trace_count": len(successful),
        }
        return self.last_reflection

    def stats(self) -> dict[str, Any]:
        traces = self.dispatcher.recent_traces(limit=200) if self.dispatcher else []
        ok = sum(1 for item in traces if item.get("ok"))
        return {"trace_count": len(traces), "success_count": ok, "fail_count": len(traces) - ok, "last_reflection": self.last_reflection}

    def _has_recent_trigger(self, trigger: str) -> bool:
        if not self.skill_store:
            return False
        now = time.time()
        for item in self.skill_store.list():
            body = item.get("body") or {}
            if str(item.get("trigger") or body.get("trigger") or "") != trigger:
                continue
            updated_at = float(item.get("updated_at") or body.get("updated_at") or body.get("created_at") or 0)
            if updated_at and now - updated_at < self.dedupe_window_seconds:
                return True
        return False

    def _last_skill_trace_cutoff(self, trigger: str) -> float:
        if not self.skill_store:
            return 0.0
        cutoff = 0.0
        for item in self.skill_store.list():
            body = item.get("body") or {}
            if str(item.get("trigger") or body.get("trigger") or "") != trigger:
                continue
            for trace in body.get("source_trace") or []:
                cutoff = max(cutoff, self._trace_ts(trace))
        return cutoff

    def _trace_ts(self, trace: dict[str, Any]) -> float:
        try:
            return float(trace.get("created_at") or trace.get("ts") or 0)
        except (TypeError, ValueError):
            return 0.0
