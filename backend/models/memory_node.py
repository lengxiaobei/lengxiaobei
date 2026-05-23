"""Memory node data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MemoryNode:
    id: str
    content: str
    type: str = "knowledge"
    parent_id: str | None = None
    summary: str | None = None
    path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: float | None = None
