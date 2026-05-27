"""Hermes-style dual-layer memory: User Profile + Memory Notes.

Two tiers injected into every system prompt:
- 'user': who the user is (preferences, identity, context)
- 'memory': agent's notes (environment facts, tool quirks, lessons)
"""

from __future__ import annotations

from typing import Any

# Char limits per tier (matching Hermes defaults)
_USER_LIMIT = 1375
_MEMORY_LIMIT = 2200


class UserProfileManager:
    """Manage user profile and memory notes stored in SQLite."""

    def __init__(self, sqlite: Any):
        self.sqlite = sqlite

    # ── Read ─────────────────────────────────────────────────────

    def get_profile(self) -> str:
        """Get formatted user profile text."""
        raw = self.sqlite.get_user_profile("user") or ""
        return raw.strip()

    def get_memory(self) -> str:
        """Get formatted memory notes text."""
        raw = self.sqlite.get_user_profile("memory") or ""
        return raw.strip()

    def inject_into_prompt(self) -> str:
        """Build the combined memory block for system prompt injection."""
        parts: list[str] = []
        profile = self.get_profile()
        memory = self.get_memory()

        if memory:
            parts.append("═" * 20 + " MEMORY (your personal notes) " + "═" * 20)
            parts.append(memory)

        if profile:
            parts.append("═" * 20 + " USER PROFILE " + "═" * 20)
            parts.append(profile)

        return "\n".join(parts) if parts else ""

    # ── Write ────────────────────────────────────────────────────

    def add(self, target: str, content: str) -> dict[str, Any]:
        """Add an entry to user profile or memory notes.

        target: 'user' or 'memory'
        content: the fact/note to add (one entry per call)
        """
        self._validate_target(target)
        existing = self.sqlite.get_user_profile(target) or ""
        limit = _USER_LIMIT if target == "user" else _MEMORY_LIMIT

        # Append as a new line
        if existing:
            updated = existing.rstrip() + "\n" + content.strip()
        else:
            updated = content.strip()

        # Enforce char limit (drop oldest entries)
        if len(updated) > limit:
            lines = updated.splitlines()
            while len("\n".join(lines)) > limit and len(lines) > 1:
                lines.pop(0)
            updated = "\n".join(lines)

        self.sqlite.set_user_profile(target, updated)
        return {"target": target, "content": content, "total_chars": len(updated)}

    def replace(self, target: str, old_text: str, new_string: str) -> dict[str, Any]:
        """Replace a substring in the target profile/memory."""
        self._validate_target(target)
        existing = self.sqlite.get_user_profile(target) or ""
        if old_text not in existing:
            return {"error": f"text not found in {target}", "old_text": old_text[:80]}
        updated = existing.replace(old_text, new_string, 1)
        self.sqlite.set_user_profile(target, updated)
        return {"target": target, "replaced": True}

    def remove(self, target: str, old_text: str) -> dict[str, Any]:
        """Remove an entry from profile/memory."""
        self._validate_target(target)
        existing = self.sqlite.get_user_profile(target) or ""
        if old_text not in existing:
            return {"error": f"text not found in {target}"}
        # Remove the line containing old_text
        lines = [line for line in existing.splitlines() if old_text not in line]
        updated = "\n".join(lines)
        self.sqlite.set_user_profile(target, updated)
        return {"target": target, "removed": True}

    def clear(self, target: str) -> dict[str, Any]:
        """Clear all entries for a target."""
        self._validate_target(target)
        self.sqlite.set_user_profile(target, "")
        return {"target": target, "cleared": True}

    # ── Internal ─────────────────────────────────────────────────

    @staticmethod
    def _validate_target(target: str) -> None:
        if target not in ("user", "memory"):
            raise ValueError(f"target must be 'user' or 'memory', got '{target}'")
