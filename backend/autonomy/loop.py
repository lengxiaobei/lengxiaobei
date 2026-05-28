"""Autonomous learning and self-improvement loop."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.autonomy.audit import AutonomyAudit
from backend.autonomy.code_quality import run_all_checks
from backend.autonomy.evolver import AutonomyEvolver
from backend.autonomy.executor import AutonomyExecutor
from backend.autonomy.goals import AutonomyGoal, default_goal_dicts
from backend.autonomy.learner import NetworkLearner


class AutonomyEngine:
    """Full project-scoped autonomy loop: learn, plan, execute, verify, evolve."""

    def __init__(
        self,
        data_dir: Path,
        memory: Any,
        dispatcher: Any,
        skill_store: Any,
        logger: Any,
        emit: Any | None = None,
        idle_check: Any | None = None,
        idle_seconds: int = 10 * 60,
        cooldown_seconds: int = 60 * 60,
        daily_budget: int = 4,
    ):
        self.data_dir = Path(data_dir)
        self.root = self.data_dir / "autonomy"
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self.memory = memory
        self.dispatcher = dispatcher
        self.skill_store = skill_store
        self.logger = logger
        self.emit = emit
        self.idle_check = idle_check
        self.idle_seconds = idle_seconds
        self.cooldown_seconds = cooldown_seconds
        self.daily_budget = daily_budget
        self.audit = AutonomyAudit(self.root / "audit.jsonl")
        self.learner = NetworkLearner()
        self.executor = AutonomyExecutor(dispatcher)
        self.evolver = AutonomyEvolver(skill_store)
        self.state = self._load_state()

    def status(self) -> dict[str, Any]:
        return {
            **self.state,
            "audit": self.audit.recent(limit=20),
            "running": True,
            "guards": self.guard_status(),
        }

    def guard_status(self) -> dict[str, Any]:
        now = time.time()
        last_run_at = float(self.state.get("last_run_at") or 0)
        today = time.strftime("%Y-%m-%d", time.localtime(now))
        budget_state = self.state.get("daily_budget") or {}
        used = int(budget_state.get("used") or 0) if budget_state.get("date") == today else 0
        idle_for = self.idle_check() if self.idle_check else None
        return {
            "idle_seconds": self.idle_seconds,
            "idle_for_seconds": idle_for,
            "cooldown_seconds": self.cooldown_seconds,
            "cooldown_remaining_seconds": max(0, int(self.cooldown_seconds - (now - last_run_at))) if last_run_at else 0,
            "daily_budget": self.daily_budget,
            "daily_budget_used": used,
        }

    async def tick(self, reason: str = "scheduled", force: bool = False, expensive_checks: bool = False) -> dict[str, Any]:
        guard = self._guard(reason=reason, force=force)
        if not guard["allowed"]:
            skipped = {"status": "skipped", "reason": reason, "guard": guard, "ts": time.time()}
            self.state["last_skip"] = skipped
            self._save_state()
            self.audit.write("tick.skipped", skipped)
            self._emit("autonomy.tick.skipped", skipped)
            return skipped
        goal = self._select_goal()
        started = time.time()
        event_payload = {"reason": reason, "goal": goal.as_dict(), "guard": guard}
        self._emit("autonomy.tick.started", event_payload)
        self.audit.write("tick.started", event_payload)

        learning = await self.learner.learn(goal.reference, limit=2)
        learning_nodes = [self._remember_learning(goal, item) for item in learning]
        roadmap = self._render_roadmap(goal, learning)
        write_result = await self.executor.write_roadmap(roadmap)

        # Run code quality checks when the active goal is code-quality-self-check
        if goal.id == "code-quality-self-check":
            checks = self._run_code_quality_checks()
            learning_nodes.append(self._remember_code_quality(goal, checks))
        else:
            checks = await self.executor.run_checks(include_expensive=expensive_checks or force)

        skill = self.evolver.draft_skill_for_goal(goal.as_dict(), learning=learning)
        changelog = await self.executor.append_changelog(
            f"\n## {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- reason: {reason}\n"
            f"- goal: {goal.id} / {goal.title}\n"
            f"- learning_nodes: {[node.get('id') for node in learning_nodes]}\n"
            f"- checks_ok: {checks.get('ok')}\n"
            f"- draft_skill: {skill.get('name')}\n"
        )

        goal.attempts += 1
        goal.status = "in_progress"
        goal.evidence.append(
            {
                "ts": time.time(),
                "reason": reason,
                "learning_ok": sum(1 for item in learning if item.get("ok")),
                "checks_ok": checks.get("ok"),
                "skill": skill.get("name"),
            }
        )
        self._save_goal(goal)

        result = {
            "status": "completed",
            "goal": goal.as_dict(),
            "learning": learning,
            "memory_nodes": learning_nodes,
            "roadmap_write": write_result,
            "checks": checks,
            "draft_skill": skill,
            "changelog": changelog,
            "elapsed_ms": round((time.time() - started) * 1000, 3),
        }
        self.state["last_run"] = result
        self.state["last_run_at"] = time.time()
        self.state["run_count"] = int(self.state.get("run_count") or 0) + 1
        self._consume_budget()
        self._save_state()
        self.audit.write("tick.completed", result)
        self._emit("autonomy.tick.completed", result)
        return result

    def _select_goal(self) -> AutonomyGoal:
        goals = [AutonomyGoal.from_dict(item) for item in self.state["goals"]]
        goals.sort(key=lambda item: (item.attempts, item.priority))
        return goals[0]

    def _save_goal(self, goal: AutonomyGoal) -> None:
        goals = []
        for item in self.state["goals"]:
            goals.append(goal.as_dict() if item["id"] == goal.id else item)
        self.state["goals"] = goals

    def _run_code_quality_checks(self) -> dict[str, Any]:
        """Run the code quality suite and return results."""
        try:
            result = run_all_checks(self.data_dir.parent)
            self.logger.info("Code quality checks: ok=%s", result.get("ok"))
            return result
        except Exception as exc:
            self.logger.exception("Code quality checks failed: %s", exc)
            return {"ok": False, "error": str(exc), "checks": []}

    def _remember_code_quality(self, goal: AutonomyGoal, checks: dict[str, Any]) -> dict[str, Any]:
        """Record code quality check results into memory."""
        content = (
            f"Autonomy code quality check for {goal.id}\n"
            f"overall_ok: {checks.get('ok')}\n"
            f"timestamp: {checks.get('timestamp')}\n"
            f"details: {json.dumps(checks.get('checks'), ensure_ascii=False, indent=2)}"
        )
        return self.memory.add_node(
            content=content,
            node_type="autonomy_code_quality",
            metadata={"goal": goal.id, "ok": checks.get("ok"), "check_count": len(checks.get("checks", []))},
            summary=f"Code quality: {'pass' if checks.get('ok') else 'fail'} ({len(checks.get('checks', []))} checks)",
        )

    def _remember_learning(self, goal: AutonomyGoal, item: dict[str, Any]) -> dict[str, Any]:
        content = (
            f"Autonomy learning for {goal.reference}/{goal.id}\n"
            f"url: {item.get('url')}\n"
            f"title: {item.get('title')}\n"
            f"ok: {item.get('ok')}\n"
            f"summary: {item.get('summary') or item.get('error')}"
        )
        return self.memory.add_node(
            content=content,
            node_type="autonomy_learning",
            metadata={"goal": goal.id, "reference": goal.reference, "url": item.get("url"), "ok": item.get("ok")},
            summary=f"{goal.reference} learning: {item.get('title')}",
        )

    def _render_roadmap(self, active_goal: AutonomyGoal, learning: list[dict[str, Any]]) -> str:
        lines = [
            "# Autonomy Roadmap",
            "",
            f"Last active goal: `{active_goal.id}` - {active_goal.title}",
            f"Reference: {active_goal.reference}",
            f"Objective: {active_goal.objective}",
            "",
            "## Learning Evidence",
        ]
        for item in learning:
            lines.append(f"- `{item.get('reference')}` {item.get('title')}: {item.get('summary') or item.get('error')}")
        lines.extend(["", "## Backlog"])
        for item in sorted(self.state["goals"], key=lambda row: row["priority"]):
            lines.append(f"- [{item.get('status')}] {item['id']}: {item['objective']}")
        return "\n".join(lines) + "\n"

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
                state.setdefault("goals", default_goal_dicts())
                state.setdefault("run_count", 0)
                state.setdefault("last_run", None)
                state.setdefault("last_run_at", None)
                state.setdefault("daily_budget", {"date": time.strftime("%Y-%m-%d"), "used": 0})
                return state
            except json.JSONDecodeError:
                self.logger.exception("autonomy state is invalid; rebuilding")
        return {"goals": default_goal_dicts(), "run_count": 0, "last_run": None, "last_run_at": None, "daily_budget": {"date": time.strftime("%Y-%m-%d"), "used": 0}}

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def _guard(self, reason: str, force: bool) -> dict[str, Any]:
        now = time.time()
        if force or reason.startswith("manual"):
            return {"allowed": True, "reason": "manual_or_forced", **self.guard_status()}
        idle_for = self.idle_check() if self.idle_check else None
        if idle_for is not None and idle_for < self.idle_seconds:
            return {"allowed": False, "reason": "not_idle", **self.guard_status()}
        last_run_at = float(self.state.get("last_run_at") or 0)
        if last_run_at and now - last_run_at < self.cooldown_seconds:
            return {"allowed": False, "reason": "cooldown", **self.guard_status()}
        if self._budget_used_today() >= self.daily_budget:
            return {"allowed": False, "reason": "daily_budget_exhausted", **self.guard_status()}
        return {"allowed": True, "reason": "guards_passed", **self.guard_status()}

    def _budget_used_today(self) -> int:
        today = time.strftime("%Y-%m-%d")
        budget = self.state.get("daily_budget") or {}
        return int(budget.get("used") or 0) if budget.get("date") == today else 0

    def _consume_budget(self) -> None:
        today = time.strftime("%Y-%m-%d")
        budget = self.state.get("daily_budget") or {}
        used = int(budget.get("used") or 0) if budget.get("date") == today else 0
        self.state["daily_budget"] = {"date": today, "used": used + 1}

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.emit:
            self.emit(event_type, payload)

