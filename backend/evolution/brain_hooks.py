"""BrainHooks — Hermes 大脑与 OpenClaw 手脚的实时铆接层。

This is the key integration layer that makes Hermes' reflection brain actively
guide OpenClaw's tool-execution body in real-time, not just on a background scheduler.

Three core responsibilities:
1. **Micro-reflection** — After EVERY tool call, instantly analyze and record what happened
2. **Failure recovery** — On tool failure, immediately diagnose → suggest fix → retry
3. **Dynamic skill injection** — Approved skills from evolution flow directly into the active tool catalog
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.evolution.skill_gen import draft_from_trace


@dataclass
class MicroInsight:
    """A micro-reflection result from a single tool execution."""
    tool: str
    ok: bool
    elapsed_ms: float
    summary: str
    next_action: str | None = None
    skill_candidate: dict[str, Any] | None = None
    error_analysis: str | None = None


@dataclass
class RecoveryAttempt:
    """Result of an automatic recovery from a tool failure."""
    tool: str
    original_error: str
    analysis: str
    fix_suggestion: str
    retry_result: Any = None
    retry_ok: bool = False
    elapsed_ms: float = 0.0


class BrainHooks:
    """Hermes brain ↔ OpenClaw body real-time integration."""

    def __init__(
        self,
        reflector: Any,
        skill_store: Any,
        memory: Any,
        dispatcher: Any | None = None,
        llm_completer: Callable | None = None,
        logger: Any = None,
        enable_recovery: bool = True,
        enable_micro_reflection: bool = True,
        enable_skill_injection: bool = True,
    ):
        self.reflector = reflector
        self.skill_store = skill_store
        self.memory = memory
        self.dispatcher = dispatcher
        self.llm_completer = llm_completer
        self.logger = logger
        self.enable_recovery = enable_recovery
        self.enable_micro_reflection = enable_micro_reflection
        self.enable_skill_injection = enable_skill_injection

        # Runtime state
        self.insights: list[MicroInsight] = []
        self.recoveries: list[RecoveryAttempt] = []
        self._last_skill_refresh: float = 0.0
        self._injected_skills: set[str] = set()
        self._tool_catalog: dict[str, Any] = {}

    # ── Public API — called by AgentLoop ─────────────────────────────

    def bind_tool_catalog(self, tools: dict[str, Any]) -> None:
        """AgentLoop calls this to let BrainHooks know what tools are available."""
        self._tool_catalog = tools

    async def on_tool_result(
        self, name: str, args: dict[str, Any], result: Any, elapsed_ms: float, ok: bool
    ) -> MicroInsight:
        """Called by AgentLoop after EVERY tool execution.

        Performs micro-reflection: analyzes what happened and records insights
        that can influence the next tool call or system prompt.
        """
        insight = MicroInsight(
            tool=name,
            ok=ok,
            elapsed_ms=elapsed_ms,
            summary=self._make_summary(name, result, ok),
        )

        if not self.enable_micro_reflection:
            self.insights.append(insight)
            return insight

        # Analyze result for next-action hints
        if ok:
            insight.next_action = self._infer_next_action(name, args, result)

        # Record in memory for long-term recall
        try:
            content = json.dumps(
                {
                    "tool": name,
                    "ok": ok,
                    "elapsed_ms": elapsed_ms,
                    "summary": insight.summary,
                    "next_action": insight.next_action,
                },
                ensure_ascii=False,
                default=str,
            )
            self.memory.add_node(
                content=content,
                node_type="micro_reflection",
                metadata={
                    "tool": name,
                    "ok": ok,
                    "elapsed_ms": elapsed_ms,
                    "reference_agent": "Hermes-Brain",
                },
                summary=insight.summary[:160],
            )
        except Exception:
            pass

        self.insights.append(insight)
        # Keep only last 100 micro-insights
        if len(self.insights) > 100:
            self.insights = self.insights[-100:]

        return insight

    async def on_tool_failure(
        self, name: str, args: dict[str, Any], error: str
    ) -> RecoveryAttempt | None:
        """Called by AgentLoop when a tool fails.

        Hermes-style recovery: analyze → suggest fix → retry.
        Returns None if recovery is disabled or not possible.
        """
        if not self.enable_recovery:
            return None

        recovery = RecoveryAttempt(
            tool=name,
            original_error=error,
            analysis="",
            fix_suggestion="",
        )

        # Step 1: Analyze the failure
        if self.llm_completer:
            recovery.analysis, recovery.fix_suggestion = await self._analyze_failure(
                name, args, error
            )
        else:
            recovery.analysis = f"工具 {name} 执行失败: {error}"
            recovery.fix_suggestion = ""
            self.recoveries.append(recovery)
            return recovery

        # Step 2: Attempt recovery if we have a fix suggestion
        if recovery.fix_suggestion and self.dispatcher:
            try:
                started = time.perf_counter()
                # Try to parse the fix suggestion as args for the same or alternative tool
                recovered = await self._attempt_recovery(
                    name, args, error, recovery.fix_suggestion
                )
                recovery.retry_result = recovered
                recovery.retry_ok = isinstance(recovered, dict) and recovered.get("ok", False)
                recovery.elapsed_ms = round((time.perf_counter() - started) * 1000)

                # If recovery worked, generate a skill candidate from this pattern
                if recovery.retry_ok and self._infer_skill_candidate(name, error):
                    try:
                        trace = [{
                            "tool": name,
                            "ok": False,
                            "error": error,
                            "args": args,
                        }, {
                            "tool": name,
                            "ok": True,
                            "args": recovered,
                        }]
                        skill = draft_from_trace(
                            name=f"recover_{name}_{int(time.time())}",
                            trigger=f"工具 {name} 失败时自动恢复",
                            trace=trace,
                        )
                        self.skill_store.save(skill)
                        self._log_info("skill saved from recovery: %s", skill.get("name"))
                    except Exception:
                        pass
            except Exception as exc:
                recovery.retry_result = {"ok": False, "error": str(exc)}
                recovery.retry_ok = False

        self.recoveries.append(recovery)
        if len(self.recoveries) > 50:
            self.recoveries = self.recoveries[-50:]

        return recovery

    def refresh_skills(self) -> dict[str, Any]:
        """Pull latest approved skills from SkillStore into the tool catalog.

        Returns newly injected skills that the AgentLoop should add.
        Called by AgentLoop before building the system prompt.
        """
        if not self.enable_skill_injection or not self.skill_store:
            return {}

        # Throttle: refresh at most once every 60 seconds
        now = time.time()
        if now - self._last_skill_refresh < 60:
            return {}
        self._last_skill_refresh = now

        new_skills: dict[str, Any] = {}
        try:
            all_skills = self.skill_store.list(status="approved")
            for skill in all_skills:
                name = skill.get("name", "")
                if not name or name in self._injected_skills:
                    continue
                if name in self._tool_catalog:
                    continue

                # Create a callable wrapper for the skill
                steps = skill.get("steps", []) or skill.get("body", {}).get("steps", [])
                if not steps:
                    continue

                wrapped = self._make_skill_callable(name, steps)
                new_skills[name] = wrapped
                self._injected_skills.add(name)
                self._log_info("injected skill: %s", name)

        except Exception as exc:
            self._log_warning("skill refresh failed: %s", exc)

        return new_skills

    def get_recent_insights(self, limit: int = 5) -> str:
        """Build a prompt snippet from recent micro-reflections to guide the LLM."""
        if not self.insights:
            return ""

        recent = self.insights[-limit:]
        lines = ["## 实时反思 (Hermes Brain)"]
        for item in recent:
            status = "✅" if item.ok else "❌"
            lines.append(f"- {status} `{item.tool}` — {item.summary}")
            if item.next_action:
                lines.append(f"  → 建议下一步: {item.next_action}")
        return "\n".join(lines) + "\n"

    def get_failure_patterns(self) -> str:
        """Detect recurring failure patterns to warn the LLM."""
        if not self.recoveries:
            return ""

        # Group failures by tool name
        by_tool: dict[str, list[RecoveryAttempt]] = {}
        for r in self.recoveries[-20:]:
            by_tool.setdefault(r.tool, []).append(r)

        patterns = []
        for tool, attempts in by_tool.items():
            if len(attempts) >= 2:
                errors = set(a.original_error[:80] for a in attempts)
                patterns.append(f"- `{tool}` 最近失败 {len(attempts)} 次: {', '.join(errors)}")

        if not patterns:
            return ""

        return "## ⚠️ 近期失败模式\n" + "\n".join(patterns) + "\n"

    # ── Internal helpers ─────────────────────────────────────────────

    def _make_summary(self, name: str, result: Any, ok: bool) -> str:
        if not ok:
            err = ""
            if isinstance(result, dict):
                err = result.get("error", "")
            return f"失败: {err}" if err else f"失败"
        if isinstance(result, dict):
            stdout = str(result.get("stdout", ""))[:100]
            if stdout:
                return f"成功: {stdout}"
            keys = list(result.keys())[:3]
            return f"成功: keys={keys}"
        if isinstance(result, str):
            return f"成功: {result[:100]}"
        return "成功"

    def _infer_next_action(
        self, name: str, args: dict[str, Any], result: Any
    ) -> str | None:
        """Infer the next tool call based on the current tool's result."""
        # Pattern-based inference (no LLM needed)
        if name == "filesystem_read":
            return "使用 filesystem_edit 或 filesystem_write 修改文件"
        if name == "shell_exec":
            if isinstance(result, dict) and result.get("returncode") != 0:
                return "分析错误输出，用 filesystem_read 查看相关源码"
            return "根据命令输出决定下一步操作"
        if name == "web_search":
            return "根据搜索结果，使用 filesystem_write 记录或 filesystem_edit 应用"
        if name in ("memory_search", "memory_recall"):
            return "基于记忆内容决定下一步行动"
        return None

    async def _analyze_failure(
        self, name: str, args: dict[str, Any], error: str
    ) -> tuple[str, str]:
        """Use LLM to analyze why a tool failed and suggest a recovery."""
        if not self.llm_completer:
            return (f"工具 {name} 失败: {error}", "")

        try:
            prompt = (
                f"## 工具执行失败\n\n"
                f"**工具**: `{name}`\n"
                f"**参数**: {json.dumps(args, ensure_ascii=False, default=str)[:500]}\n"
                f"**错误**: {error[:500]}\n\n"
                f"你是冷小北的 Hermes 恢复引擎。分析失败原因，给出立即可执行的修复方案。\n\n"
                f"返回 JSON（只返回 JSON）:\n"
                f'{{"analysis": "失败原因分析", "fix": "具体的修复方案"}}\n\n'
                f"修复方案要具体到：改用哪个工具、调整什么参数、或者分步骤如何处理。"
            )

            system = "你是冷小北的恢复分析器。给出具体、可执行、不需要再确认的方案。"
            reply = await self.llm_completer(prompt, system=system)

            # Parse JSON from reply
            reply = reply.strip()
            if reply.startswith("```"):
                reply = reply.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            try:
                parsed = json.loads(reply)
                return (
                    parsed.get("analysis", ""),
                    parsed.get("fix", ""),
                )
            except json.JSONDecodeError:
                # If not valid JSON, treat the whole reply as analysis
                return (reply[:500], "")
        except Exception as exc:
            return (f"分析失败: {exc}", "")

    async def _attempt_recovery(
        self, name: str, args: dict[str, Any], error: str, fix_suggestion: str
    ) -> Any:
        """Attempt to execute the fix suggestion through the dispatcher."""
        # Common recovery patterns
        # Pattern 1: old_string not found → re-read file and retry
        if "old_string" in error or "not found" in fix_suggestion.lower():
            if "filesystem_read" in str(self._tool_catalog):
                # Suggest re-reading
                return await self.dispatcher.dispatch("filesystem_read", {
                    "path": args.get("path", "."),
                })

        # Pattern 2: Shell command failed → try with corrected args
        if name == "shell_exec" and "命令" in fix_suggestion:
            return {"ok": False, "error": f"需要手动修正: {fix_suggestion[:200]}"}

        # Generic: try the LLM's suggestion as a shell command
        if fix_suggestion and name == "shell_exec":
            return await self.dispatcher.dispatch("shell_exec", {
                "command": fix_suggestion[:500],
            })

        return {"ok": False, "error": f"无法自动恢复: {fix_suggestion[:200]}"}

    def _infer_skill_candidate(self, name: str, error: str) -> bool:
        """Decide if this failure pattern is worth turning into a skill."""
        # Only create skills for common, recoverable error patterns
        recoverable_patterns = [
            "not found",
            "SyntaxError",
            "ModuleNotFoundError",
            "ImportError",
            "Connection refused",
        ]
        return any(p in error for p in recoverable_patterns)

    def _make_skill_callable(self, name: str, steps: list[dict]) -> Callable:
        """Create a callable wrapper that executes skill steps through dispatcher."""

        async def _execute(args: dict[str, Any] | None = None) -> dict[str, Any]:
            results = []
            dispatcher = self.dispatcher
            if not dispatcher:
                return {"ok": False, "error": "dispatcher not available", "results": results}

            for step in steps:
                tool = step.get("tool", "")
                step_args = dict(step.get("args", {}))
                # Merge user-provided args
                if args:
                    step_args.update(args)
                try:
                    obs = await dispatcher.dispatch(tool, step_args)
                    results.append(obs)
                    if not obs.get("ok"):
                        return {"ok": False, "error": f"step failed: {tool}", "results": results}
                except Exception as exc:
                    return {"ok": False, "error": str(exc), "results": results}

            return {"ok": True, "results": results}

        _execute.__name__ = name
        _execute.__doc__ = f"动态技能: {name} (由 Hermes 进化引擎生成)"
        return _execute

    def _log_info(self, msg: str, *args: Any) -> None:
        if self.logger:
            self.logger.info(msg, *args)

    def _log_warning(self, msg: str, *args: Any) -> None:
        if self.logger:
            self.logger.warning(msg, *args)
