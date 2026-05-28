"""User profile data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserProfile:
    id: str
    display_name: str = ""
    preferences: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
