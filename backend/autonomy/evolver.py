"""Autonomous skill evolution."""

from __future__ import annotations

import time
from typing import Any

from backend.evolution.skill_gen import draft_skill


class AutonomyEvolver:
    def __init__(self, skill_store: Any):
        self.skill_store = skill_store

    def draft_skill_for_goal(self, goal: dict[str, Any], learning: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Draft a skill informed by actual learning evidence instead of hardcoded steps."""
        # Build steps from learning evidence when available
        steps = []
        if learning:
            for item in learning:
                if item.get("ok") and item.get("summary"):
                    title = item.get("title", "reference")
                    summary = item.get("summary", "")[:200]
                    steps.append(f"Apply insight from {title}: {summary}")

        # Always include core autonomy steps as fallback
        if not steps:
            steps = [
                f"Review goal: {goal['title']}",
                "Fetch reference material through NetworkLearner",
            ]
        steps.extend([
            "Write learning notes into MemoryTree",
            "Run project checks through shell_exec",
            "Record audit event and update autonomy roadmap",
        ])

        # Include evidence from goal's own history
        evidence_sources = []
        for ev in (goal.get("evidence") or [])[-3:]:
            if ev.get("skill"):
                evidence_sources.append({"goal": goal["id"], "previous_skill": ev["skill"], "ts": ev.get("ts")})

        skill = draft_skill(
            name=f"autonomy_{goal['id']}",
            trigger=f"autonomy:{goal['id']}",
            steps=steps,
            source_trace=evidence_sources or [{"goal": goal, "ts": time.time()}],
        )
        self.skill_store.save(skill)
        return skill

