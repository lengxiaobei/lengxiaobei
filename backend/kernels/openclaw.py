"""Read-only channel runtime lane.

The internal id is still "openclaw" for compatibility; user-facing behavior is
LengXiaobei's native gateway/channel/tool capability.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from backend.agents.integrations import OpenClawIntegration
from backend.kernels.base import Capability, KernelAdapter, KernelHealth, TaskEnvelope, TaskResult


class OpenClawAdapter(KernelAdapter):
    name = "openclaw"

    def __init__(self, home: Path | None = None):
        self.integration = OpenClawIntegration(home=home)

    async def health(self) -> KernelHealth:
        status = await self.integration.status() or {}
        installed = bool(status.get("installed"))
        gateway = status.get("gateway") or {}
        gateway_online = bool(status.get("gateway_online"))
        compatible = bool(status.get("gateway_compatible"))
        callable_ok = installed and gateway_online and compatible
        if callable_ok:
            public_status = "healthy"
            message = "通道运行时在线，可执行只读巡检。"
        elif installed and gateway_online:
            public_status = "degraded"
            message = "通道网关在线，但协议仍需适配。"
        elif installed:
            public_status = "offline"
            message = "已发现兼容网关目录，但网关离线。"
        else:
            public_status = "offline"
            message = "未发现兼容网关目录；冷小北原生通道仍可继续运行。"
        return KernelHealth(
            kernel="openclaw",
            installed=installed,
            reachable=gateway_online,
            callable=callable_ok,
            status=public_status,
            public_message=message,
            details={
                "gateway_online": gateway_online,
                "gateway_compatible": compatible,
                "protocol": gateway.get("protocol") or status.get("protocol"),
                "agents_count": status.get("agents_count") or 0,
                "port": gateway.get("port"),
            },
        )

    async def capabilities(self) -> list[Capability]:
        health = await self.health()
        return [
            Capability("openclaw.gateway.status", "openclaw", "查看网关状态", "检查冷小北通道网关是否在线。", enabled=health.installed),
            Capability("openclaw.channel.inspect", "openclaw", "巡检通道", "只读检查网关、通道、插件与工具状态。", enabled=health.installed),
            Capability("openclaw.plugin.list", "openclaw", "查看插件", "查看插件能力概览。", enabled=health.installed),
            Capability("openclaw.tool.list", "openclaw", "查看工具能力", "查看通道运行时暴露的工具能力。", enabled=health.installed),
            Capability("openclaw.gateway.restart", "openclaw", "重启网关", "重启冷小北通道网关。", risk="high", requires_confirmation=True, enabled=False),
        ]

    async def submit(self, task: TaskEnvelope) -> TaskResult:
        if task.capability in {"openclaw.gateway.status", "openclaw.channel.inspect", "openclaw.plugin.list", "openclaw.tool.list"}:
            health = await self.health()
            observations = [health.public_dict()]
            if health.status == "healthy":
                summary = f"通道网关在线，协议已兼容；当前可做只读巡检。已发现 {health.details.get('agents_count', 0)} 个兼容配置。"
                next_actions = ["继续观察插件和通道告警", "需要执行任务时先走冷小北权限层"]
                status = "completed"
            elif health.reachable:
                summary = "通道网关在线，但当前协议仍未完全兼容；暂不执行任务分发。"
                next_actions = ["查看网关版本", "保持只读模式，避免修改兼容网关配置"]
                status = "failed"
            else:
                summary = "兼容网关目录已发现但网关离线；通道、插件和多入口分发暂不可用。"
                next_actions = ["先启动通道网关", "启动后重新执行通道巡检"]
                status = "failed"
            return TaskResult(task.id, status, "openclaw", summary, observations, next_actions)
        return TaskResult(task.id, "unsupported", "openclaw", "这个通道运行时能力尚未开放。", [], ["当前仅开放只读巡检能力"])

    def _port_open(self, port: int | None) -> bool:
        if not port:
            return False
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=0.25):
                return True
        except OSError:
            return False
