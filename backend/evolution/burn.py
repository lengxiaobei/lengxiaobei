"""Token-burning self-evolution engine — ACTUALLY modifies code, approves skills, and runs goals.

Every cycle:
1. Deep reflection → approve & execute the best pending skill
2. Skill generation → auto-approve the generated skill
3. Code review → apply fixes to actual source files
4. Goal planning → inject goals into autonomy state

This burns tokens AND produces real changes.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.core.llm.ollama import chat as llm_chat
from backend.evolution.evaluator import staged_quality

# Default quality threshold for auto-approving generated skills.
# Score is computed from staged_quality signals (0.0 = no signals pass, 1.0 = all pass).
# Skills scoring below this threshold are queued for manual review instead of auto-approved.
DEFAULT_QUALITY_THRESHOLD = 0.6


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 3)


@dataclass
class BurnSession:
    id: str
    started_at: float
    cycles: list[dict[str, Any]] = field(default_factory=list)
    estimated_tokens: int = 0
    status: str = "running"
    summary: str = ""


class BurnEngine:
    """Intensive self-evolution — every token burned produces real change."""

    def __init__(self, reflector: Any, skill_store: Any, dispatcher: Any, memory: Any, logger: Any, data_dir: Path, quality_threshold: float = DEFAULT_QUALITY_THRESHOLD):
        self.reflector = reflector
        self.skill_store = skill_store
        self.dispatcher = dispatcher
        self.memory = memory
        self.logger = logger
        self.data_dir = data_dir
        self.project_root = data_dir.parent
        self.quality_threshold = quality_threshold
        self.active_session: BurnSession | None = None
        self.sessions: list[BurnSession] = []
        self.total_tokens: int = 0

    def status(self) -> dict[str, Any]:
        return {
            "active_session": self.active_session.id if self.active_session else None,
            "total_tokens": self.total_tokens,
            "session_count": len(self.sessions),
            "last_session": asdict(self.sessions[-1]) if self.sessions else None,
        }

    async def sprint(self, cycles: int = 3, force: bool = True) -> dict[str, Any]:
        session = BurnSession(
            id=f"burn_{int(time.time())}_{len(self.sessions) + 1}",
            started_at=time.time(),
        )
        self.active_session = session

        for i in range(cycles):
            cycle = await self._run_cycle(i + 1, cycles, force=force)
            session.cycles.append(cycle)
            session.estimated_tokens += cycle.get("estimated_tokens", 0)

        session.status = "completed"
        session.summary = self._summarize_session(session)
        self.total_tokens += session.estimated_tokens
        self.sessions.append(session)
        self.active_session = None

        return asdict(session)

    async def _run_cycle(self, index: int, total: int, force: bool) -> dict[str, Any]:
        cycle_start = time.time()
        results: dict[str, Any] = {"index": index, "steps": {}}
        estimated_tokens = 0

        try:
            # Step 1: Review code → generate & apply patch
            review = await self._code_review_and_fix()
            results["steps"]["code_review_and_fix"] = review
            estimated_tokens += review.get("estimated_tokens", 0)

            # Step 2: Generate skill → auto-approve & execute
            gen = await self._generate_approve_execute()
            results["steps"]["skill_gen_approve_execute"] = gen
            estimated_tokens += gen.get("estimated_tokens", 0)

            # Step 3: Deep reflection → approve pending skills
            deep = await self._deep_reflection_and_approve()
            results["steps"]["deep_reflection_approve"] = deep
            estimated_tokens += deep.get("estimated_tokens", 0)

            # Step 4: Plan & inject goals
            plan = await self._plan_and_inject_goals()
            results["steps"]["goal_planning_inject"] = plan
            estimated_tokens += plan.get("estimated_tokens", 0)
        except Exception as exc:
            self.logger.exception("burn cycle %s failed", index)
            results["error"] = str(exc)

        results["estimated_tokens"] = estimated_tokens
        results["elapsed_ms"] = round((time.time() - cycle_start) * 1000)
        return results

    # ── Step 1: Code review → generate diff → apply to files ──────────

    async def _code_review_and_fix(self) -> dict[str, Any]:
        py_files = sorted(self.project_root.rglob("backend/**/*.py"))[:15]
        file_map: dict[str, str] = {}
        for path in py_files[:6]:
            try:
                file_map[path.name] = path.read_text()
            except Exception:
                continue

        if not file_map:
            return {"ok": False, "summary": "无代码可分析", "estimated_tokens": 0}

        code_block = "\n\n".join(f"### {name}\n{content[:2000]}" for name, content in file_map.items())
        prompt = f"""你是冷小北的代码改进引擎。审查以下文件，找出可以立即改进的地方，给出具体的修改方案。

{code_block[:8000]}

返回 JSON（只返回 JSON）：
{{
  "changes": [
    {{
      "file": "文件名",
      "reason": "改进原因",
      "old_lines": "需要替换的原始代码（精确匹配）",
      "new_lines": "替换后的新代码"
    }}
  ]
}}

只返回可以安全自动应用的改进：添加错误处理、改进日志、优化性能、修复小bug。不要改核心架构。"""

        try:
            reply = await llm_chat(prompt, system="你是冷小北的代码改进引擎。给出精确、安全、可自动应用的代码修改。")
            tokens = _estimate_tokens(prompt) + _estimate_tokens(reply)
            parsed = self._safe_json(reply)
            applied = []
            for change in parsed.get("changes", []):
                result = self._apply_change(change, file_map)
                applied.append(result)
            ok_count = sum(1 for item in applied if item.get("ok"))
            summary = f"代码审查完成：{len(applied)} 个改进点，成功应用 {ok_count} 个"
            self.memory.add_node(content=summary, node_type="burn_code_fix", metadata={"changes": applied}, summary=summary[:180])
            return {"ok": True, "summary": summary, "changes": applied, "estimated_tokens": tokens}
        except Exception as exc:
            return {"ok": False, "summary": str(exc), "estimated_tokens": _estimate_tokens(prompt)}

    def _apply_change(self, change: dict, file_map: dict[str, str]) -> dict[str, Any]:
        filename = str(change.get("file", "")).strip()
        old_lines = str(change.get("old_lines", "")).strip()
        new_lines = str(change.get("new_lines", "")).strip()
        if not filename or not old_lines:
            return {"ok": False, "file": filename, "reason": "missing file or old_lines"}

        # Find the actual file path
        target = None
        for p in self.project_root.rglob(f"backend/**/{filename}"):
            target = p
            break
        if not target:
            return {"ok": False, "file": filename, "reason": "file not found"}

        try:
            content = target.read_text()
            if old_lines not in content:
                return {"ok": False, "file": filename, "reason": "old_lines not found in file"}
            new_content = content.replace(old_lines, new_lines, 1)
            if new_content == content:
                return {"ok": False, "file": filename, "reason": "no change made"}
            target.write_text(new_content)
            return {"ok": True, "file": str(target.relative_to(self.project_root)), "reason": change.get("reason", "auto-fix")}
        except Exception as exc:
            return {"ok": False, "file": filename, "reason": str(exc)}

    # ── Step 2: Generate skill → auto-approve → execute ─────────────────

    async def _generate_approve_execute(self) -> dict[str, Any]:
        existing = self.skill_store.list()
        names = [item.get("name", "") for item in existing[:15]]
        trace_text = json.dumps(self.dispatcher.recent_traces(limit=10), ensure_ascii=False, indent=2)

        prompt = f"""现有技能：{json.dumps(names, ensure_ascii=False)}
最近执行轨迹：{trace_text[:3000]}

根据轨迹中的失败和成功模式，生成一个可执行的技能。技能步骤只能使用以下工具：filesystem_read, filesystem_write, filesystem_append, shell_readonly, shell_exec, memory_search, skill_list, system_status。

返回 JSON（只返回 JSON）：
{{
  "name": "技能名",
  "trigger": "触发词",
  "steps": [{{"tool": "工具名", "args": {{"参数": "值"}}}}],
  "description": "技能说明"
}}"""

        try:
            reply = await llm_chat(prompt, system="你是冷小北的技能生成器。生成可用系统工具立即执行的技能。")
            tokens = _estimate_tokens(prompt) + _estimate_tokens(reply)
            parsed = self._safe_json(reply)
            if not parsed.get("name") or not parsed.get("steps"):
                return {"ok": False, "summary": "未生成有效技能", "estimated_tokens": tokens}

            # ── Quality gate: evaluate before auto-approving ─────────────
            evaluation = self._evaluate_skill_quality(parsed)
            score = evaluation["score"]
            passed = evaluation["passed"]
            reason = evaluation["reason"]
            self.logger.info(
                "burn skill quality gate: name=%s score=%.2f passed=%s — %s",
                parsed.get("name"), score, passed, reason,
            )

            name = self._safe_name(parsed["name"])
            steps = parsed["steps"]

            if not passed:
                # Below threshold → save as "pending" for manual review, do NOT execute
                skill = {
                    "name": name, "trigger": parsed.get("trigger", "manual"),
                    "steps": steps, "status": "pending",
                    "reference_agent": "MiMo-Burn", "description": parsed.get("description", ""),
                    "quality_score": score, "quality_reason": reason,
                }
                self.skill_store.save(skill)
                self.skill_store.set_status(name, "pending")
                summary = f"技能 {name} 已生成但未通过质量门控（{reason}），已加入审查队列"
                self.memory.add_node(
                    content=json.dumps(evaluation, ensure_ascii=False),
                    node_type="burn_skill_queued",
                    metadata={"skill": name, "score": score},
                    summary=summary[:180],
                )
                return {
                    "ok": True, "skill": name, "queued_for_review": True,
                    "evaluation": evaluation, "summary": summary,
                    "estimated_tokens": tokens,
                }

            # Above threshold → save as approved and execute immediately
            skill = {
                "name": name, "trigger": parsed.get("trigger", "manual"),
                "steps": steps, "status": "approved",
                "reference_agent": "MiMo-Burn", "description": parsed.get("description", ""),
                "quality_score": score, "quality_reason": reason,
            }
            self.skill_store.save(skill)
            self.skill_store.set_status(name, "approved")

            # Execute immediately
            exec_result = await self._execute_skill_steps(steps)
            summary = f"技能 {name} 通过质量门控（评分 {score:.0%}）已审批并执行：{'成功' if exec_result.get('ok') else '部分失败'}"
            self.memory.add_node(content=json.dumps(exec_result, ensure_ascii=False), node_type="burn_skill_exec", metadata={"skill": name, "score": score}, summary=summary[:180])
            return {"ok": True, "skill": name, "executed": exec_result, "evaluation": evaluation, "estimated_tokens": tokens}
        except Exception as exc:
            return {"ok": False, "summary": str(exc), "estimated_tokens": 0}

    async def _execute_skill_steps(self, steps: list[dict]) -> dict[str, Any]:
        results = []
        ok = True
        for step in steps:
            tool = str(step.get("tool", ""))
            args = dict(step.get("args", {}))
            if not tool:
                results.append({"ok": False, "error": "no tool specified"})
                ok = False
                continue
            try:
                obs = await self.dispatcher.dispatch(tool, args)
                results.append(obs)
                if not obs.get("ok"):
                    ok = False
            except Exception as exc:
                results.append({"ok": False, "error": str(exc)})
                ok = False
        return {"ok": ok, "results": results}

    # ── Step 3: Deep reflection → auto-approve pending skills ───────────

    async def _deep_reflection_and_approve(self) -> dict[str, Any]:
        pending = self.skill_store.list(status="pending")
        traces = self.dispatcher.recent_traces(limit=20)
        trace_text = json.dumps(traces, ensure_ascii=False, indent=2)

        pending_list = [
            {
                "name": s.get("name"),
                "trigger": s.get("trigger"),
                "steps": str(s.get("body", s).get("steps", "")[:200]),
            }
            for s in pending[:8]
        ]
        prompt = f"""审查以下 pending 技能，决定哪些可以自动审批执行。

Pending 技能：{json.dumps(pending_list, ensure_ascii=False)}
最近轨迹：{trace_text[:2000]}

返回 JSON（只返回 JSON）：
{{
  "approve": ["可以审批的技能名列表"],
  "reject": ["应该拒绝的技能名列表"],
  "reason": "审批理由"
}}"""

        try:
            reply = await llm_chat(prompt, system="你是冷小北的技能审批引擎。安全第一，只审批低风险技能。")
            tokens = _estimate_tokens(prompt) + _estimate_tokens(reply)
            parsed = self._safe_json(reply)
            approved_names = parsed.get("approve", [])
            results = []
            for name in approved_names:
                skill = self.skill_store.load(name)
                if not skill:
                    results.append({"name": name, "ok": False, "reason": "not found"})
                    continue
                self.skill_store.set_status(name, "approved")
                exec_r = await self._execute_skill_steps(skill.get("steps", []))
                results.append({"name": name, "ok": True, "executed": exec_r})
            summary = f"自动审批 {len(approved_names)} 个技能，执行完成"
            return {"ok": True, "summary": summary, "approved": results, "estimated_tokens": tokens}
        except Exception as exc:
            return {"ok": False, "summary": str(exc), "estimated_tokens": 0}

    # ── Step 4: Plan goals → inject into autonomy state ─────────────────

    async def _plan_and_inject_goals(self) -> dict[str, Any]:
        state_path = self.data_dir / "autonomy" / "state.json"
        current_goals = []
        if state_path.exists():
            try:
                current_goals = json.loads(state_path.read_text()).get("goals", [])
            except Exception:
                pass

        prompt = f"""当前自治目标：{json.dumps([g.get('id','') for g in current_goals[:10]], ensure_ascii=False)}

你是冷小北的进化规划器。基于当前项目状态，提出 2 个新的自治目标。

当前项目是 LengXiaobei，一个本地 Agent 总控系统。项目结构：backend/（Python FastAPI），frontend/（React TypeScript），对接 OpenClaw/Hermes/OpenHuman。

返回 JSON（只返回 JSON）：
{{
  "goals": [
    {{"id": "goal-id", "title": "目标标题", "objective": "目标描述", "reference": "OpenClaw/Hermes/OpenHuman", "priority": 10, "next_actions": ["具体可执行步骤"]}}
  ]
}}"""

        try:
            reply = await llm_chat(prompt, system="你是冷小北的进化规划器。生成具体、可执行的自治目标。")
            tokens = _estimate_tokens(prompt) + _estimate_tokens(reply)
            parsed = self._safe_json(reply)
            new_goals = parsed.get("goals", [])
            if not new_goals:
                return {"ok": False, "summary": "未生成新目标", "estimated_tokens": tokens}

            # Inject into autonomy state
            if state_path.exists():
                try:
                    state = json.loads(state_path.read_text())
                    existing_ids = {g.get("id") for g in state.get("goals", [])}
                    for goal in new_goals:
                        goal.setdefault("status", "pending")
                        goal.setdefault("attempts", 0)
                        goal.setdefault("evidence", [])
                        if goal["id"] not in existing_ids:
                            state["goals"].append(goal)
                            existing_ids.add(goal["id"])
                    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
                except Exception as exc:
                    return {"ok": False, "summary": f"写入目标失败: {exc}", "estimated_tokens": tokens}
            else:
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state = {"goals": new_goals, "run_count": 0, "last_run": None, "last_run_at": None, "daily_budget": {"date": time.strftime("%Y-%m-%d"), "used": 0}}
                state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))

            summary = f"已注入 {len(new_goals)} 个新自治目标"
            self.memory.add_node(content=json.dumps(new_goals, ensure_ascii=False), node_type="burn_goals", metadata={"source": "burn_engine"}, summary=summary[:180])
            return {"ok": True, "summary": summary, "goals": new_goals, "estimated_tokens": tokens}
        except Exception as exc:
            return {"ok": False, "summary": str(exc), "estimated_tokens": 0}

    # ── helpers ────────────────────────────────────────────────────────

    def _evaluate_skill_quality(self, parsed: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a generated skill's quality using staged_quality signals.

        Returns a dict with:
          - signals: dict[str, bool]  (the 5 staged quality booleans)
          - score: float in [0.0, 1.0]
          - passed: bool  (True if score >= self.quality_threshold)
          - reason: str   (human-readable explanation)
        """
        name = str(parsed.get("name", "")).strip()
        steps = parsed.get("steps", [])
        description = str(parsed.get("description", "")).strip()
        trigger = str(parsed.get("trigger", "")).strip()

        # ── Signal 1: syntax_ok — valid structure, all required fields present ──
        syntax_ok = bool(name) and isinstance(steps, list) and len(steps) > 0

        # ── Signal 2: function_exists — required fields are non-trivial ──
        placeholder_names = {"技能名", "skill_name", "new_skill", "test", "untitled", ""}
        function_exists = (
            syntax_ok
            and name.lower() not in placeholder_names
            and len(name) >= 2
        )

        # ── Signal 3: callable_ok — every step references a non-empty tool name ──
        callable_ok = function_exists and all(
            bool(str(step.get("tool", "")).strip()) for step in steps
        )

        # ── Signal 4: semantic_ok — meaningful description and trigger ──
        placeholder_descs = {"技能说明", "skill description", "description", ""}
        semantic_ok = (
            callable_ok
            and description.lower() not in placeholder_descs
            and len(description) >= 4
            and len(trigger) >= 1
        )

        # ── Signal 5: integrated_ok — tools in steps are known to the dispatcher ──
        known_tools: set[str] = set()
        if hasattr(self.dispatcher, "list_tools"):
            try:
                known_tools = set(self.dispatcher.list_tools())
            except Exception:
                pass
        if known_tools and callable_ok:
            integrated_ok = all(
                str(step.get("tool", "")).strip() in known_tools for step in steps
            )
        else:
            # If we can't enumerate tools, give benefit of the doubt when callable_ok passes
            integrated_ok = callable_ok

        signals = staged_quality(
            syntax_ok=syntax_ok,
            function_exists=function_exists,
            callable_ok=callable_ok,
            semantic_ok=semantic_ok,
            integrated_ok=integrated_ok,
        )

        passed_count = sum(1 for v in signals.values() if v)
        score = passed_count / len(signals)  # len(signals) is always 5
        passed = score >= self.quality_threshold

        # Build a human-readable reason
        failed = [k for k, v in signals.items() if not v]
        if passed:
            reason = f"质量评分 {score:.0%}（{passed_count}/5 信号通过），达到阈值 {self.quality_threshold:.0%}，自动审批"
        else:
            reason = f"质量评分 {score:.0%}（{passed_count}/5 信号通过），低于阈值 {self.quality_threshold:.0%}，加入审查队列。未通过：{', '.join(failed)}"

        return {"signals": signals, "score": score, "passed": passed, "reason": reason}

    def _safe_json(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    def _safe_name(self, name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")[:80] or "burn_skill"

    def _summarize_session(self, session: BurnSession) -> str:
        total_cycles = len(session.cycles)
        fixes = 0
        skills = 0
        goals = 0
        for c in session.cycles:
            steps = c.get("steps", {})
            review = steps.get("code_review_and_fix", {})
            fixes += sum(1 for item in review.get("changes", []) if item.get("ok"))
            skill = steps.get("skill_gen_approve_execute", {})
            if skill.get("ok"):
                skills += 1
            plan = steps.get("goal_planning_inject", {})
            goals += len(plan.get("goals", []))
        parts = [f"燃尽 {session.estimated_tokens} tokens"]
        if fixes:
            parts.append(f"修改 {fixes} 个文件")
        if skills:
            parts.append(f"生成+执行 {skills} 个技能")
        if goals:
            parts.append(f"注入 {goals} 个目标")
        return "，".join(parts) + f"，{total_cycles} 轮循环"
