"""Autonomy goals for native LengXiaobei capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AutonomyGoal:
    id: str
    title: str
    reference: str
    objective: str
    priority: int
    status: str = "pending"
    attempts: int = 0
    evidence: list[dict[str, Any]] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "reference": self.reference,
            "objective": self.objective,
            "priority": self.priority,
            "status": self.status,
            "attempts": self.attempts,
            "evidence": self.evidence,
            "next_actions": self.next_actions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutonomyGoal":
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            reference=str(data["reference"]),
            objective=str(data["objective"]),
            priority=int(data.get("priority") or 100),
            status=str(data.get("status") or "pending"),
            attempts=int(data.get("attempts") or 0),
            evidence=list(data.get("evidence") or []),
            next_actions=list(data.get("next_actions") or []),
        )


DEFAULT_GOALS = [
    AutonomyGoal(
        id="capability-parity-spine",
        title="Native capability spine",
        reference="LengXiaobei",
        objective=(
            "Build OpenClaw/Hermes/OpenHuman-inspired capability classes inside LengXiaobei itself: "
            "project authority, internal orchestration, reflection, skill verification, durable memory, "
            "identity, and cross-channel continuity."
        ),
        priority=1,
        next_actions=[
            "Map native LengXiaobei gaps against the reference capability classes",
            "Pick one missing closed-loop capability",
            "Implement or draft the smallest verifiable increment",
            "Record evidence in roadmap, changelog, memory, or tests",
        ],
    ),
    AutonomyGoal(
        id="openclaw-tool-authority",
        title="Project-scoped write/execute authority",
        reference="LengXiaobei native authority",
        objective="Give LengXiaobei powerful project-scoped tool execution for self-modification while preserving root boundaries and audit traces.",
        priority=10,
        next_actions=["Inspect tool traces", "Run project checks", "Propose next guarded tool"],
    ),
    AutonomyGoal(
        id="openclaw-channel-runtime",
        title="Production channel runtime",
        reference="LengXiaobei native channels",
        objective="Turn LengXiaobei's optional Telegram/WhatsApp/Slack boundaries into observable, reconnecting channel runtimes.",
        priority=20,
        next_actions=["Study local channel runtime patterns", "Draft lifecycle checks", "Add channel health events"],
    ),
    AutonomyGoal(
        id="openhuman-memory-graph",
        title="Memory graph enrichment",
        reference="LengXiaobei native memory",
        objective="Improve LengXiaobei's MemoryTree with entity extraction, timeline links, graph edges, and editable provenance.",
        priority=30,
        next_actions=["Learn graph memory patterns", "Index recent memories", "Draft entity extraction skill"],
    ),
    AutonomyGoal(
        id="openhuman-sync-connectors",
        title="Real sync connectors",
        reference="LengXiaobei native sync",
        objective="Upgrade LengXiaobei's placeholder sync connectors into authenticated incremental sync jobs with conflict handling.",
        priority=40,
        next_actions=["Fetch connector docs", "Draft connector contract", "Add sync status validation"],
    ),
    AutonomyGoal(
        id="hermes-skill-verification",
        title="Skill verification loop",
        reference="LengXiaobei native skills",
        objective="Promote LengXiaobei-generated skills only after replay, tests, evaluation, and rollback metadata are available.",
        priority=50,
        next_actions=["Inspect recent traces", "Generate pending verifier skill", "Run skill store checks"],
    ),
    AutonomyGoal(
        id="hermes-reflection-evaluator",
        title="Reflection and evaluator depth",
        reference="LengXiaobei native reflection",
        objective="Convert LengXiaobei's raw reflections into measurable hypotheses, pass/fail criteria, and versioned improvements.",
        priority=60,
        next_actions=["Reflect on latest failures", "Persist evaluation notes", "Draft evaluator roadmap"],
    ),
    AutonomyGoal(
        id="code-quality-self-check",
        title="Periodic code quality self-check",
        reference="LengXiaobei",
        objective=(
            "Run automated code quality checks (compile, tests, anti-patterns, missing tests, large files) "
            "and record trends. Propose fixes when checks fail."
        ),
        priority=15,
        next_actions=["Run code quality suite", "Record check results in memory", "Propose fix for failing checks"],
    ),
]


def default_goal_dicts() -> list[dict[str, Any]]:
    return [goal.as_dict() for goal in DEFAULT_GOALS]
