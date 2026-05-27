"""Read-only reflection/skill lane.

The internal id is still "hermes" for compatibility; user-facing behavior is
LengXiaobei's native reflection and skill verification capability.
"""

from __future__ import annotations

from pathlib import Path

from backend.agents.integrations import HermesIntegration
from backend.kernels.base import Capability, KernelAdapter, KernelHealth, TaskEnvelope, TaskResult


class HermesAdapter(KernelAdapter):
    name = "hermes"

    def __init__(self, home: Path | None = None):
        self.integration = HermesIntegration(home=home)

    async def health(self) -> KernelHealth:
        status = await self.integration.status()
        ok = bool(status.get("ok"))
        installed = bool((status.get("profile") or {}).get("root")) and not status.get("error", "").startswith("[Errno 2]")
        if ok:
            public_status = "healthy"
            message = "反思技能链路可用：可分析、可自省。"
        elif installed:
            public_status = "degraded"
            message = "已发现兼容技能目录，但运行入口需要检查。"
        else:
            public_status = "offline"
            message = "未发现兼容技能入口；冷小北原生反思仍可继续运行。"
        return KernelHealth(
            kernel="hermes",
            installed=installed,
            reachable=ok,
            callable=ok,
            status=public_status,
            public_message=message,
            details={"skills_count": status.get("skills_count"), "mode": status.get("mode") or "python-module"},
        )

    async def capabilities(self) -> list[Capability]:
        health = await self.health()
        return [
            Capability("hermes.task.submit", "hermes", "提交长任务", "交给冷小北反思技能链路规划复杂任务。", risk="medium", enabled=health.callable),
            Capability("hermes.skill.list", "hermes", "查看技能", "查看冷小北技能概览。", enabled=health.installed),
            Capability("hermes.diagnose.failure", "hermes", "分析失败原因", "基于巡检结果做失败归因。", risk="medium", enabled=health.installed),
            Capability("hermes.reflect", "hermes", "自省总结", "总结近期轨迹和改进建议。", risk="medium", enabled=health.installed),
            Capability("hermes.plan", "hermes", "生成执行计划", "为复杂任务生成执行计划。", risk="medium", enabled=health.installed),
        ]

    async def submit(self, task: TaskEnvelope) -> TaskResult:
        health = await self.health()
        if task.capability == "hermes.diagnose.failure":
            source = task.context.get("source_summary") or "暂无巡检结果。"
            if not health.installed:
                return TaskResult(task.id, "failed", "hermes", "反思技能链路当前不可用，无法进行失败分析。", [health.public_dict()], ["先确认技能运行入口"])
            summary = f"冷小北反思技能链路已进入只读分析模式。初步判断：{source} 建议先确认网关在线状态、协议兼容性和最近一次任务错误。"
            return TaskResult(task.id, "completed", "hermes", summary, [health.public_dict()], ["保留巡检结果", "必要时再开放长任务执行"])
        return TaskResult(task.id, "unsupported", "hermes", "MVP 当前仅开放反思技能只读诊断入口。", [health.public_dict()], ["下一阶段再开放长任务提交"])
