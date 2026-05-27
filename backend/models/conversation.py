"""Conversation data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ConversationMessage:
    id: str
    role: Literal["user", "assistant", "system"]
    text: str
    channel: str = "web"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float | None = None
