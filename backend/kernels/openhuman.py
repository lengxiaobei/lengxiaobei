"""Read-only memory continuity lane.

The internal id is still "openhuman" for compatibility; user-facing behavior is
LengXiaobei's native memory, profile, and preference capability.
"""

from __future__ import annotations

from pathlib import Path

from backend.agents.integrations import OpenHumanIntegration
from backend.kernels.base import Capability, KernelAdapter, KernelHealth, TaskEnvelope, TaskResult


class OpenHumanAdapter(KernelAdapter):
    name = "openhuman"

    def __init__(self, home: Path | None = None):
        self.integration = OpenHumanIntegration(home=home)

    async def health(self) -> KernelHealth:
        status = await self.integration.status()
        installed = bool(status.get("ok"))
        active = bool(status.get("active_user_id"))
        if installed and active:
            public_status = "healthy"
            message = "只读记忆可用。"
        elif installed:
            public_status = "degraded"
            message = "已发现兼容记忆目录，但没有激活用户。"
        else:
            public_status = "offline"
            message = "未发现兼容记忆目录；冷小北原生记忆仍可继续运行。"
        return KernelHealth(
            kernel="openhuman",
            installed=installed,
            reachable=installed,
            callable=installed and active,
            status=public_status,
            public_message=message,
            details={"active_user": active, "auth_profiles_count": status.get("auth_profiles_count")},
        )

    async def capabilities(self) -> list[Capability]:
        health = await self.health()
        return [
            Capability("openhuman.profile.read", "openhuman", "读取用户画像摘要", "只读读取用户画像摘要，不展示敏感原文。", risk="medium", enabled=health.callable),
            Capability("openhuman.memory.search", "openhuman", "搜索长期记忆", "只读搜索长期记忆摘要。", risk="medium", enabled=health.callable),
            Capability("openhuman.context.current", "openhuman", "当前上下文", "读取当前上下文摘要。", risk="medium", enabled=health.callable),
            Capability("openhuman.preference.read", "openhuman", "工作偏好", "读取工作偏好摘要。", risk="medium", enabled=health.callable),
        ]

    async def submit(self, task: TaskEnvelope) -> TaskResult:
        health = await self.health()
        if task.capability in {"openhuman.profile.read", "openhuman.preference.read", "openhuman.context.current"}:
            if not health.callable:
                return TaskResult(task.id, "failed", "openhuman", health.public_message, [health.public_dict()], ["先确认 OpenHuman 激活用户"])
            summary = "OpenHuman 只读上下文可用。MVP 暂只返回安全摘要，不展示原始个人数据。"
            return TaskResult(task.id, "completed", "openhuman", summary, [health.public_dict()], ["后续可把偏好摘要接入调度策略"])
        return TaskResult(task.id, "unsupported", "openhuman", "MVP 当前仅开放记忆连续性只读摘要能力。", [health.public_dict()], [])
