"""Unified local kernel adapter contracts for LengXiaobei."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

KernelId = Literal["openclaw", "hermes", "openhuman"]
HealthStatus = Literal["healthy", "degraded", "offline", "unknown"]
RiskLevel = Literal["low", "medium", "high", "critical"]
TaskStatus = Literal["completed", "failed", "queued", "needs_confirmation", "unsupported"]


@dataclass
class KernelHealth:
    kernel: KernelId
    installed: bool
    reachable: bool
    callable: bool
    status: HealthStatus
    public_message: str
    mode: str = "只读模式"
    details: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Capability:
    id: str
    owner: KernelId
    title: str
    description: str
    risk: RiskLevel = "low"
    requires_confirmation: bool = False
    enabled: bool = True

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskEnvelope:
    goal: str
    target: KernelId
    capability: str
    priority: str = "normal"
    risk: RiskLevel = "low"
    requires_confirmation: bool = False
    context: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"task_{int(time.time())}_{uuid.uuid4().hex[:8]}")

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    owner: KernelId
    summary: str
    observations: list[dict[str, Any]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class KernelAdapter:
    name: KernelId

    async def health(self) -> KernelHealth:
        raise NotImplementedError

    async def capabilities(self) -> list[Capability]:
        raise NotImplementedError

    async def submit(self, task: TaskEnvelope) -> TaskResult:
        raise NotImplementedError
