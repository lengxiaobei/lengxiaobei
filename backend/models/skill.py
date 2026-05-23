"""Skill data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class SkillRecord:
    name: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    trigger: str = "manual"
    path: str | None = None
    body: dict[str, Any] = field(default_factory=dict)
    success_count: int = 0
    fail_count: int = 0
