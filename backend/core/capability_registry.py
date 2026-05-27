"""Capability registry for LengXiaobei native capability lanes.

The historical adapter names are kept as stable internal ids, but the user-facing
concept is native capability inside LengXiaobei, not downstream agents to control.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from backend.kernels import HermesAdapter, KernelAdapter, OpenClawAdapter, OpenHumanAdapter, TaskEnvelope


class CapabilityRegistry:
    def __init__(self, home: Path | None = None):
        self.adapters: dict[str, KernelAdapter] = {
            "openclaw": OpenClawAdapter(home=home),
            "hermes": HermesAdapter(home=home),
            "openhuman": OpenHumanAdapter(home=home),
        }
        self.recent_results: list[dict[str, Any]] = []

    async def kernels(self) -> list[dict[str, Any]]:
        return [(await adapter.health()).public_dict() for adapter in self.adapters.values()]

    async def capabilities(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for adapter in self.adapters.values():
            items.extend([capability.public_dict() for capability in await adapter.capabilities()])
        items.append({
            "id": "native.inspect_then_diagnose",
            "owner": "hermes",
            "title": "巡检后诊断",
            "description": "先由冷小北通道运行时做只读巡检，再由反思技能链路分析失败原因。",
            "risk": "medium",
            "requires_confirmation": False,
            "enabled": True,
        })
        return items

    async def tasks(self, limit: int = 12) -> list[dict[str, Any]]:
        return list(reversed(self.recent_results[-limit:]))

    async def submit(self, task: TaskEnvelope | dict[str, Any]) -> dict[str, Any]:
        envelope = task if isinstance(task, TaskEnvelope) else TaskEnvelope(**task)
        if envelope.capability == "native.inspect_then_diagnose":
            result = await self._inspect_then_diagnose(envelope)
            self._record_result(result)
            return result
        adapter = self.adapters.get(envelope.target)
        if not adapter:
            result = {
                "task_id": envelope.id,
                "status": "failed",
                "owner": envelope.target,
                "summary": "未找到对应的本地 Agent。",
                "observations": [],
                "next_actions": ["检查任务目标是否正确"],
            }
            self._record_result(result)
            return result
        result = (await adapter.submit(envelope)).public_dict()
        self._record_result(result)
        return result

    async def match(self, goal: str) -> TaskEnvelope | None:
        text = "".join(goal.lower().split())
        if "hermes" in text and "openclaw" in text and any(word in text for word in ("失败", "分析", "诊断", "原因", "巡检结果")):
            return TaskEnvelope(goal=goal, target="hermes", capability="native.inspect_then_diagnose", risk="medium")
        if "openclaw" in text and any(word in text for word in ("巡检", "通道", "gateway", "网关", "插件", "工具")):
            return TaskEnvelope(goal=goal, target="openclaw", capability="openclaw.channel.inspect")
        if any(word in text for word in ("三套agent状态", "三套状态", "agent状态", "查看三套")):
            return TaskEnvelope(goal=goal, target="openclaw", capability="openclaw.gateway.status")
        if "hermes" in text and any(word in text for word in ("失败", "分析", "诊断", "原因")):
            return TaskEnvelope(goal=goal, target="hermes", capability="hermes.diagnose.failure", risk="medium")
        if "openhuman" in text and any(word in text for word in ("偏好", "画像", "上下文", "记忆")):
            return TaskEnvelope(goal=goal, target="openhuman", capability="openhuman.preference.read", risk="medium")
        return None

    async def _inspect_then_diagnose(self, envelope: TaskEnvelope) -> dict[str, Any]:
        inspect_task = TaskEnvelope(
            goal="先执行冷小北通道运行时只读巡检",
            target="openclaw",
            capability="openclaw.channel.inspect",
            context={"source": "collaboration", "parent_task": envelope.id},
        )
        openclaw_result = (await self.adapters["openclaw"].submit(inspect_task)).public_dict()
        diagnose_task = TaskEnvelope(
            goal=envelope.goal,
            target="hermes",
            capability="hermes.diagnose.failure",
            risk="medium",
            context={
                "source": "collaboration",
                "parent_task": envelope.id,
                "source_summary": openclaw_result.get("summary"),
                "source_status": openclaw_result.get("status"),
            },
        )
        hermes_result = (await self.adapters["hermes"].submit(diagnose_task)).public_dict()
        status = "completed" if hermes_result.get("status") == "completed" else "failed"
        summary = "协作诊断完成：" + str(hermes_result.get("summary") or "冷小北反思技能链路已处理巡检结果。")
        observations = [
            {"stage": "openclaw.inspect", "result": openclaw_result},
            {"stage": "hermes.diagnose", "result": hermes_result},
        ]
        next_actions = []
        next_actions.extend(openclaw_result.get("next_actions") or [])
        next_actions.extend(hermes_result.get("next_actions") or [])
        return {
            "task_id": envelope.id,
            "status": status,
            "owner": "hermes",
            "summary": summary,
            "observations": observations,
            "next_actions": next_actions[:6],
        }

    def _record_result(self, result: dict[str, Any]) -> None:
        safe = {
            "task_id": result.get("task_id"),
            "status": result.get("status"),
            "owner": result.get("owner"),
            "summary": result.get("summary"),
            "next_actions": result.get("next_actions") or [],
            "created_at": time.time(),
        }
        self.recent_results.append(safe)
        del self.recent_results[:-50]
