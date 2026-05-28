"""Event-driven autonomous agent loop for LengXiaobei.

Receives user messages → runs memory recall → LLM decides tools to call →
executes tools → feeds results back → LLM continues → ... → writes back memory.

The core loop is MULTI-TURN: the LLM can call multiple tools in sequence,
see results, and decide what to do next — just like a human developer would.

Model-agnostic: works with any LLM (Ollama, Token-plan, Claude, etc.).
Tool calls use a simple text format, not provider-specific JSON.
"""

from __future__ import annotations

import asyncio
import enum
import inspect
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from backend.memory.sqlite_backend import SQLiteMemoryBackend
from backend.config import get_settings
from backend.evolution.brain_hooks import BrainHooks


# ── State Machine Phases ────────────────────────────────────────

class Phase(str, enum.Enum):
    """Agent execution phases. Flows: IDLE→DIAGNOSE→PLAN→EXECUTE→VERIFY→REFLECT"""
    IDLE = "idle"
    DIAGNOSE = "diagnose"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
    REFLECT = "reflect"


# Phase transition rules:
#   DIAGNOSE  → PLAN (analysis done)
#   PLAN      → EXECUTE (plan ready)
#   EXECUTE   → VERIFY (tools executed)
#   VERIFY    → REFLECT (verified) or DIAGNOSE (failed, retry)
#   DIAGNOSE  → REFLECT (max failures reached)

PHASE_TRANSITIONS = {
    Phase.DIAGNOSE: Phase.PLAN,
    Phase.PLAN: Phase.EXECUTE,
    Phase.EXECUTE: Phase.VERIFY,
    Phase.VERIFY: Phase.REFLECT,  # on success; on failure → DIAGNOSE
}

MAX_PHASE_FAILURES = 3  # After this many failures in VERIFY, force REFLECT


class LLMCallFailedError(Exception):
    """Raised when the LLM completer call fails (network error, timeout, etc.).

    This distinguishes infrastructure failures from the model legitimately
    returning empty content, so callers can handle each case appropriately.
    """

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


# ── Tool call format (model-agnostic) ───────────────────────────────
# The LLM outputs tool calls in this format:
#
#   <tool name="filesystem_read">
#   {"path": "backend/core/commander.py"}
#   </tool>
#
# Some models also produce:
#
#   <tool_call>
#   <tool_name>filesystem_read</tool_name>
#   <args>{"path": "backend/core/commander.py"}</args>
#   </tool_call>
#
# This works with ANY LLM that can follow instructions — no need for
# Claude's JSON tool_use or OpenAI's function_calling format.

TOOL_CALL_RE = re.compile(
    r'<tool\s+name=["\']([^"\']+)["\']>\s*(.*?)\s*</tool>',
    re.DOTALL,
)
XML_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*<tool_name>\s*(.*?)\s*</tool_name>\s*<args>\s*(.*?)\s*</args>\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)
LEGACY_FUNCTION_TOOL_CALL_RE = re.compile(
    r"<tool_call>.*?</tool_call>",
    re.DOTALL | re.IGNORECASE,
)

TOOL_RESULT_TEMPLATE = (
    '<tool_result name="{name}">\n{result}\n</tool_result>'
)


@dataclass
class ToolSpec:
    """Model-facing metadata for one runtime tool."""

    name: str
    description: str = ""
    category: str = "general"
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnResult:
    """Result of a single agent loop run (may involve multiple tool calls)."""

    reply: str
    tool_calls: list[dict[str, Any]]
    recall_count: int
    goals_updated: bool
    elapsed_ms: float
    iterations: int = 0
    run_id: str = ""


@dataclass
class AgentConfig:
    """Configuration for the agent loop."""

    max_turns_per_session: int = 20
    max_tool_rounds: int = 10       # Max tool-call iterations per request
    recall_limit: int = 12
    tool_timeout_seconds: float = 30.0
    memory_promotion_interval_seconds: float = 30 * 60
    goal_check_interval_seconds: float = 10 * 60
    prune_threshold: int = 5000
    max_phase_failures: int = MAX_PHASE_FAILURES


@dataclass
class RunState:
    """Tracks the state machine progress for a single agent run."""

    phase: Phase = Phase.IDLE
    round_num: int = 0
    failure_count: int = 0
    phase_failure_count: int = 0  # Cumulative failures across VERIFY→DIAGNOSE cycles
    max_phase_failures: int = MAX_PHASE_FAILURES
    all_tool_calls: list = field(default_factory=list)
    tool_observations: list = field(default_factory=list)
    conversation: list = field(default_factory=list)
    final_reply: str = ""
    run_id: str = ""

    def transition(self, to: Phase) -> None:
        """Move to a new phase. Failure count persists across DIAGNOSE retries."""
        self.phase = to

    def record_failure(self) -> None:
        """Record a tool failure. Increments both counters."""
        self.failure_count += 1
        self.phase_failure_count += 1

    @property
    def should_force_reflect(self) -> bool:
        """True if too many failures — force REFLECT instead of retry."""
        return self.phase_failure_count >= self.max_phase_failures


class AgentLoop:
    """Self-contained agent loop with memory, goals, and iterative tool dispatch.

    The key difference from the old AgentLoop:
    - handle() now runs a multi-turn loop: LLM → tool call → result → LLM → ...
    - The LLM decides what tools to call based on results it sees
    - This mirrors how a human developer works: read → think → edit → verify → fix
    """

    def __init__(
        self,
        memory: SQLiteMemoryBackend | None = None,
        config: AgentConfig | None = None,
        llm_completer: Any = None,
        tools: dict[str, Any] | None = None,
        logger: Any = None,
        brain_hooks: BrainHooks | None = None,
        trace_backend: Any = None,
        context_compressor: Any = None,
        fact_extractor: Any = None,
    ) -> None:
        self.memory = memory or SQLiteMemoryBackend()
        self.config = config or AgentConfig()
        self.tools = tools or {}
        self.tool_specs: dict[str, ToolSpec] = {}
        self.llm_completer = llm_completer
        self.logger = logger or self._make_logger()
        self.brain_hooks = brain_hooks
        self.trace = trace_backend  # SQLiteBackend for trace writing
        self.context_compressor = context_compressor
        self.fact_extractor = fact_extractor

        # Runtime state
        self._turn_count: int = 0
        self._session_started_at: float = time.time()
        self._last_activity_at: float = time.time()
        self._active_goals: list[dict[str, Any]] = []

        # Background tasks
        self._bg_tasks: list[asyncio.Task] = []
        self._running = False

    # ── Public API ────────────────────────────────────────────────────

    async def run(self) -> None:
        """Start background loops (goal check, memory promotion)."""
        self._running = True
        self._bg_tasks = [
            asyncio.create_task(self._goal_check_loop()),
            asyncio.create_task(self._memory_promotion_loop()),
        ]
        self.logger.info("AgentLoop started")

    async def stop(self) -> None:
        self._running = False
        for t in self._bg_tasks:
            t.cancel()
        self.logger.info("AgentLoop stopped")

    async def handle(self, text: str, channel: str = "web") -> TurnResult:
        """Process one user message through the state machine agent loop.

        Phases: IDLE → DIAGNOSE → PLAN → EXECUTE → VERIFY → REFLECT
        On VERIFY failure: → DIAGNOSE (retry with failure context)
        After max failures: → REFLECT (give up and summarize)
        """
        started = time.time()
        self._last_activity_at = time.time()
        self._turn_count += 1

        # ── Initialize state machine ──
        state = RunState(phase=Phase.DIAGNOSE, max_phase_failures=self.config.max_phase_failures)

        # ── Trace: start run ──
        if self.trace:
            state.run_id = self.trace.trace_start_run(text, channel)

        # 1. Write user message to memory
        self.memory.add_node(
            content=text,
            node_type="conversation",
            metadata={"role": "user", "channel": channel, "turn": self._turn_count},
            summary=text[:120],
        )

        # 2. Recall relevant context
        recall = self._recall(text)

        # 3. BrainHooks refresh
        if self.brain_hooks:
            self.brain_hooks.bind_tool_catalog(self.tools)
            new_skills = self.brain_hooks.refresh_skills()
            if new_skills:
                for skill_name, skill_fn in new_skills.items():
                    self.register_tool(skill_name, skill_fn, category="dynamic_skill",
                                      description=f"动态进化技能: {skill_name}")

        # 4. State machine loop
        state.conversation = [{"role": "user", "content": text}]
        llm_response = ""  # Initialize to avoid unbound error

        while state.round_num < self.config.max_tool_rounds:
            state.round_num += 1
            step_started = time.time()

            # Compress context if conversation gets too long
            if self.context_compressor and len(state.conversation) > 10:
                state.conversation = await self.context_compressor.maybe_compress(state.conversation)

            # Build phase-aware system prompt
            system_prompt = self._build_system_prompt(recall, phase=state.phase, state=state)

            # Call LLM
            llm_call_failed = False
            try:
                llm_response = await self._call_llm(state.conversation, system_prompt)
            except LLMCallFailedError as exc:
                self.logger.warning("LLM call failed in round %d: %s", state.round_num, exc)
                llm_response = ""
                llm_call_failed = True

            # Handle empty LLM response
            if not llm_response:
                if state.round_num == 1:
                    summary_conv = list(state.conversation)
                    summary_conv.append({"role": "user", "content": "请基于上方工具执行结果，用中文给出简洁的总结和结论。"})
                    try:
                        retry = await self._call_llm(summary_conv, system_prompt)
                    except LLMCallFailedError:
                        retry = ""
                    if retry and retry.strip():
                        state.final_reply = retry.strip()
                        break
                state.final_reply = self._fallback_reply_from_tool_observations(state.tool_observations)
                if not state.final_reply:
                    if llm_call_failed:
                        state.final_reply = "模型调用失败，请稍后重试或检查 LLM 后端连接。"
                    else:
                        state.final_reply = "模型接口已连通，但返回了空内容。"
                break

            # Parse tool calls
            tool_calls = self._parse_tool_calls(llm_response)

            # ── Trace: record step ──
            step_id = ""
            if self.trace and state.run_id:
                step_id = self.trace.trace_add_step(
                    state.run_id, state.round_num,
                    phase=state.phase.value,
                    tool_calls_count=len(tool_calls),
                )

            # No tool calls → LLM is done
            if not tool_calls:
                state.final_reply = self._strip_tool_tags(llm_response)
                # Transition to next phase based on current phase
                if state.phase == Phase.DIAGNOSE:
                    state.transition(Phase.PLAN)
                    # PLAN phase just re-asks LLM with plan context
                    state.conversation.append({"role": "assistant", "content": llm_response})
                    state.conversation.append({"role": "user", "content": "计划已明确，请立即执行修改。"})
                    continue
                elif state.phase == Phase.PLAN:
                    state.transition(Phase.EXECUTE)
                    state.conversation.append({"role": "assistant", "content": llm_response})
                    state.conversation.append({"role": "user", "content": "请执行修改。"})
                    continue
                elif state.phase == Phase.EXECUTE:
                    state.transition(Phase.VERIFY)
                    state.conversation.append({"role": "assistant", "content": llm_response})
                    state.conversation.append({"role": "user", "content": "修改完成，请验证结果。"})
                    continue
                else:
                    # VERIFY or REFLECT → done
                    break

            # Execute tool calls
            tool_results_text = ""
            has_failures = False
            for tc in tool_calls:
                state.all_tool_calls.append(tc)
                tool_started = time.time()
                result = await self._execute_tool(tc["name"], tc["args"])
                tool_elapsed = (time.time() - tool_started) * 1000
                ok = not (isinstance(result, dict) and result.get("error"))

                if not ok:
                    has_failures = True
                    state.record_failure()

                # ── Trace: record tool call ──
                if self.trace and state.run_id:
                    error_msg = ""
                    if not ok and isinstance(result, dict):
                        error_msg = str(result.get("error", ""))
                    self.trace.trace_add_tool_call(
                        state.run_id, tc["name"], tc["args"], result,
                        step_id=step_id, ok=ok, error=error_msg,
                        elapsed_ms=tool_elapsed,
                    )
                    # Record failure pattern for auto-learning
                    if not ok and error_msg and self.trace:
                        try:
                            self.trace.record_failure_pattern(
                                pattern=f"tool:{tc['name']}:{error_msg[:100]}",
                                tool=tc["name"],
                                error_signature=error_msg[:200],
                            )
                        except Exception as exc:
                            self.logger.debug("Failed to record failure pattern for tool %s: %s", tc["name"], exc)

                # ── BrainHooks ──
                if self.brain_hooks:
                    await self.brain_hooks.on_tool_result(
                        tc["name"], tc["args"], result, tool_elapsed, ok,
                    )
                    if not ok:
                        error_text = str(result.get("error", "unknown")) if isinstance(result, dict) else str(result)
                        recovery = await self.brain_hooks.on_tool_failure(
                            tc["name"], tc["args"], error_text,
                        )
                        if recovery and recovery.retry_ok:
                            self.logger.info("auto-recovery succeeded for %s", tc["name"])
                            result = recovery.retry_result
                            ok = True
                            has_failures = False

                state.tool_observations.append({"tool": tc["name"], "args": tc["args"], "result": result})
                result_text = json.dumps(result, ensure_ascii=False, default=str)
                if len(result_text) > 4000:
                    result_text = result_text[:4000] + "\n... (truncated)"
                tool_results_text += TOOL_RESULT_TEMPLATE.format(
                    name=tc["name"], result=result_text
                ) + "\n"

            # ── Phase transition after tool execution ──
            if has_failures and state.phase == Phase.VERIFY:
                # Verification failed → back to DIAGNOSE
                if state.should_force_reflect:
                    # Too many failures → force REFLECT
                    state.transition(Phase.REFLECT)
                    state.conversation.append({"role": "assistant", "content": llm_response})
                    state.conversation.append({"role": "user", "content": (
                        f"验证失败（已重试 {state.phase_failure_count} 次）。"
                        "请直接总结：做了什么、哪里失败了、可能的原因。"
                    )})
                else:
                    state.transition(Phase.DIAGNOSE)
                    state.conversation.append({"role": "assistant", "content": llm_response})
                    state.conversation.append({"role": "user", "content": tool_results_text + "\n验证失败，请重新诊断问题。"})
            elif not has_failures and state.phase == Phase.VERIFY:
                # Verify succeeded → REFLECT
                state.transition(Phase.REFLECT)
                state.conversation.append({"role": "assistant", "content": llm_response})
                state.conversation.append({"role": "user", "content": tool_results_text + "\n验证通过，请给出最终回复。"})
            else:
                # Normal transition: feed results back
                next_phase = PHASE_TRANSITIONS.get(state.phase, Phase.EXECUTE)
                state.transition(next_phase)
                state.conversation.append({"role": "assistant", "content": llm_response})
                state.conversation.append({"role": "user", "content": tool_results_text})

        # 5. Finalize
        if not state.final_reply:
            state.final_reply = self._strip_tool_tags(llm_response) if llm_response else ""
        if not state.final_reply:
            state.final_reply = self._fallback_reply_from_tool_observations(state.tool_observations)
        if not state.final_reply:
            state.final_reply = "模型接口已连通，但最终回复为空；请换一种说法或让我直接执行诊断。"

        state.final_reply = state.final_reply.strip()

        # 6. Write to memory
        self.memory.add_node(
            content=state.final_reply,
            node_type="conversation",
            metadata={"role": "assistant", "channel": channel, "turn": self._turn_count,
                      "tool_calls": state.all_tool_calls, "iterations": state.round_num,
                      "phase": state.phase.value, "failures": state.failure_count},
            summary=state.final_reply[:120],
        )

        # 7. Update goals
        goals_updated = self._update_goals(text, state.final_reply)

        elapsed_ms = (time.time() - started) * 1000

        # ── Trace: finish run ──
        if self.trace and state.run_id:
            status = "completed" if not state.failure_count else "completed_with_errors"
            self.trace.trace_finish_run(
                state.run_id, status=status, final_reply=state.final_reply[:500],
                total_tool_calls=len(state.all_tool_calls), total_steps=state.round_num,
                elapsed_ms=elapsed_ms,
            )
            if state.failure_count > 0:
                self.trace.trace_add_reflection(
                    state.run_id,
                    diagnosis=f"任务完成但有 {state.failure_count} 个工具调用失败（经历 {state.phase.value} 阶段）",
                    kind="auto",
                    trigger="tool_failure",
                    lesson=f"共 {len(state.all_tool_calls)} 次工具调用，{state.failure_count} 次失败",
                )

        # Extract facts from conversation for long-term memory
        if self.fact_extractor and state.final_reply:
            try:
                await self.fact_extractor.maybe_extract(text, state.final_reply[:1000])
            except Exception as exc:
                self.logger.warning("Failed to extract facts from conversation: %s", exc, exc_info=True)

        return TurnResult(
            reply=state.final_reply,
            tool_calls=state.all_tool_calls,
            recall_count=len(recall),
            goals_updated=goals_updated,
            elapsed_ms=elapsed_ms,
            iterations=state.round_num,
            run_id=state.run_id,
        )

    # ── System prompt with tool descriptions ─────────────────────────

    def _build_system_prompt(self, recall: list[dict[str, Any]], phase: Phase = Phase.DIAGNOSE, state: RunState | None = None) -> str:
        """Build system prompt including tool documentation, recalled memory, and phase guidance."""
        tool_docs = self._tool_descriptions()
        recall_text = self._build_recall_prompt(recall)

        # ── Hermes Brain: real-time insights and failure patterns ──
        brain_context = ""
        if self.brain_hooks:
            insights = self.brain_hooks.get_recent_insights(limit=5)
            failures = self.brain_hooks.get_failure_patterns()
            if insights:
                brain_context += insights + "\n"
            if failures:
                brain_context += failures + "\n"

        # ── Phase-specific guidance ──
        phase_guide = self._phase_guidance(phase, state)

        return (
            "你是冷小北，运行在 LengXiaobei 本地优先智能体框架中。\n"
            "你拥有完整的代码修改能力：读写文件、精确编辑、运行测试和命令。\n"
            "你的核心优势是可以自主执行修复循环：诊断→定位→编辑→验证。\n\n"
            "## 工具调用格式\n\n"
            "通过以下 XML 标签调用工具（参数必须是合法 JSON）：\n\n"
            '<tool name="工具名">\n{"参数": "值"}\n</tool>\n\n'
            f"{phase_guide}\n"
            "## 工具调用失败的处理\n\n"
            "**filesystem_edit 失败时（old_string not found）**：\n"
            "- 不要放弃，不要换方法，直接重新 filesystem_read 获取文件精确内容\n"
            "- 从新的工具输出里复制 old_string 的**精确文本**（包括所有空格和缩进）\n"
            "- 然后用相同的 filesystem_edit 重试\n"
            "- 如果多次失败，改用 filesystem_read + filesystem_write 完整重写整个文件\n\n"
            "**其他工具失败时**：分析错误信息，重新选择工具重试\n\n"
            "## 可用工具\n\n"
            f"{tool_docs}\n\n"
            f"{brain_context}"
            "## 重要原则\n\n"
            "- 优先用 filesystem_edit 而非 filesystem_write：精确替换，不要全文覆盖\n"
            "- 修复前必须先读懂上下文，不要盲改\n"
            "- 测试/验证命令必须实际运行，返回结果再分析\n"
            "- 遇到 .py 文件报 SyntaxError，先读源码确认问题再改\n"
            "- 不能读写 .env 文件，不能访问项目外路径\n"
            "- 关注「实时反思」中的建议，利用「近期失败模式」避免重复犯错\n\n"
            f"{recall_text}\n"
            "回答要简洁、直接、有主见。中文优先。"
        )

    def _phase_guidance(self, phase: Phase, state: RunState | None = None) -> str:
        """Return phase-specific workflow instructions."""
        failure_hint = ""
        if state and state.phase_failure_count > 0:
            failure_hint = f"\n注意：当前已失败 {state.phase_failure_count} 次，请仔细分析之前的错误再行动。"

        if phase == Phase.DIAGNOSE:
            return (
                "## 当前阶段：诊断（DIAGNOSE）\n\n"
                "你的任务是**理解问题**，不要急着修改代码。\n"
                "1. 用 code_search/shell_exec 定位问题所在\n"
                "2. 用 filesystem_read 读取相关源码\n"
                "3. 分析根因，给出诊断结论\n"
                "诊断完成后，说明你打算怎么修复，然后开始执行。"
                f"{failure_hint}"
            )
        elif phase == Phase.PLAN:
            return (
                "## 当前阶段：规划（PLAN）\n\n"
                "基于诊断结果，制定修复计划：\n"
                "1. 需要修改哪些文件\n"
                "2. 每个文件改什么（具体到函数/行）\n"
                "3. 预期修改后的效果\n"
                "计划明确后，立即开始执行。"
                f"{failure_hint}"
            )
        elif phase == Phase.EXECUTE:
            return (
                "## 当前阶段：执行（EXECUTE）\n\n"
                "按计划执行修改：\n"
                "1. 用 filesystem_edit 做精确替换\n"
                "2. 每次修改后不要验证，继续下一个修改\n"
                "3. 所有修改完成后进入验证阶段\n"
                "注意：优先用 filesystem_edit，不要全文覆盖。"
                f"{failure_hint}"
            )
        elif phase == Phase.VERIFY:
            return (
                "## 当前阶段：验证（VERIFY）\n\n"
                "验证修改是否正确：\n"
                "1. 用 shell_exec 运行测试/检查\n"
                "2. 检查输出是否符合预期\n"
                "3. 如果发现问题，回到诊断阶段重新分析\n"
                "验证通过后，给出最终回复。"
                f"{failure_hint}"
            )
        elif phase == Phase.REFLECT:
            return (
                "## 当前阶段：反思（REFLECT）\n\n"
                "总结本次任务：\n"
                "1. 做了什么\n"
                "2. 结果如何\n"
                "3. 学到了什么（成功经验或失败教训）\n"
                "直接给出最终回复。"
            )
        else:
            return "## 代码修改工作流\n\n修复类请求的标准流程：诊断→读源码→精确编辑→验证→修复。"

    def _tool_descriptions(self) -> str:
        """Generate tool documentation for the system prompt."""
        by_category: dict[str, list[str]] = {}
        for name in sorted(self.tools):
            spec = self.tool_specs.get(name)
            if spec:
                description = spec.description
                schema = f" 参数: {json.dumps(spec.input_schema, ensure_ascii=False)}" if spec.input_schema else ""
                line = f"- **{name}**: {description}{schema}".strip()
                category = spec.category
            else:
                fn = self.tools[name]
                doc = (fn.__doc__ or "").strip().split("\n")[0]
                line = f"- **{name}**: {doc}" if doc else f"- **{name}**"
                category = "general"
            by_category.setdefault(category, []).append(line)
        sections = []
        for category in sorted(by_category):
            sections.append(f"### {category}")
            sections.extend(by_category[category])
        return "\n".join(sections)

    # ── Tool call parsing (model-agnostic) ───────────────────────────

    def _parse_tool_calls(self, text: str) -> list[dict[str, Any]]:
        """Parse supported model-agnostic tool-call blocks from LLM output."""
        calls = []
        for match in TOOL_CALL_RE.finditer(text):
            name = match.group(1).strip()
            args_text = match.group(2).strip()
            calls.append({"name": name, "args": self._parse_tool_args(args_text)})
        for match in XML_TOOL_CALL_RE.finditer(text):
            name = match.group(1).strip()
            args_text = match.group(2).strip()
            calls.append({"name": name, "args": self._parse_tool_args(args_text)})
        return calls

    def _parse_tool_args(self, args_text: str) -> dict[str, Any]:
        try:
            return json.loads(args_text) if args_text else {}
        except json.JSONDecodeError:
            return {"raw_input": args_text}

    def _strip_tool_tags(self, text: str) -> str:
        """Remove tool-call blocks from LLM output for the final reply."""
        stripped = TOOL_CALL_RE.sub("", text)
        stripped = XML_TOOL_CALL_RE.sub("", stripped)
        stripped = LEGACY_FUNCTION_TOOL_CALL_RE.sub("", stripped)
        return stripped.strip()

    def _fallback_reply_from_tool_observations(self, observations: list[dict[str, Any]]) -> str:
        """Produce a user-facing reply when the model only emitted tool calls."""
        if not observations:
            return ""
        lines = ["我执行了诊断工具，但模型最终回复为空；这里是工具结果摘要："]
        for item in observations[-5:]:
            tool = item.get("tool", "unknown")
            result = item.get("result")
            if isinstance(result, dict):
                if result.get("error"):
                    summary = f"失败：{result.get('error')}"
                elif "stdout" in result or "stderr" in result:
                    stdout = str(result.get("stdout") or "").strip()
                    stderr = str(result.get("stderr") or "").strip()
                    returncode = result.get("returncode")
                    output = stdout or stderr or "无输出"
                    summary = f"returncode={returncode}，{output[:240]}"
                elif result.get("ok") is not None:
                    summary = json.dumps(result, ensure_ascii=False, default=str)[:240]
                else:
                    summary = json.dumps(result, ensure_ascii=False, default=str)[:240]
            else:
                summary = str(result)[:240]
            lines.append(f"- {tool}: {summary}")
        return "\n".join(lines)

    # ── Tool execution ────────────────────────────────────────────────

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Execute a named tool with timeout."""
        tool = self.tools.get(name)
        if not tool:
            return {"error": f"unknown tool: {name}. Available: {', '.join(sorted(self.tools))}"}
        try:
            # Tools can be sync or async
            result = tool(args)
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=self.config.tool_timeout_seconds)
            return result
        except asyncio.TimeoutError:
            return {"error": f"tool {name} timed out after {self.config.tool_timeout_seconds}s"}
        except Exception as exc:
            self.logger.warning("tool %s failed: %s", name, exc)
            return {"error": str(exc)}

    # ── LLM calling ──────────────────────────────────────────────────

    async def _call_llm(self, conversation: list[dict[str, str]], system: str) -> str:
        """Call the configured LLM with conversation history.

        Raises:
            LLMCallFailedError: If the LLM completer raises an exception.
                Callers should catch this to distinguish from empty model output.
        """
        if self.llm_completer is None:
            return self._fallback_reply_from_conversation(conversation)

        try:
            result = self.llm_completer(
                prompt=conversation[-1]["content"],
                system=system,
                history=conversation,
            )
            if inspect.isawaitable(result):
                result = await result
            return str(result)
        except Exception as exc:
            self.logger.warning("llm_completer failed: %s", exc)
            raise LLMCallFailedError(
                f"LLM completer call failed: {exc}", original_error=exc,
            ) from exc

    def _fallback_reply_from_conversation(self, conversation: list[dict[str, str]]) -> str:
        """Generate a basic reply when no LLM is available."""
        last = conversation[-1]["content"] if conversation else ""
        # Check if there are tool results waiting for interpretation
        if "<tool_result" in last:
            return "工具已执行，但当前无 LLM 后端来解读结果。原始输出见上方。"
        return f"收到：{last[:100]}...（当前无 LLM 后端，使用默认回复）"

    # ── Memory ────────────────────────────────────────────────────────

    def _recall(self, text: str) -> list[dict[str, Any]]:
        """Fetch recent and semantically relevant memory nodes."""
        candidates: list[dict[str, Any]] = []
        if text:
            candidates.extend(self.memory.search(text, limit=self.config.recall_limit))
        candidates.extend(self.memory.list_recent(limit=self.config.recall_limit))
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in candidates:
            item_id = str(item.get("id") or "")
            if item_id in seen:
                continue
            seen.add(item_id)
            result.append(item)
            if len(result) >= self.config.recall_limit:
                break
        return result

    def _build_recall_prompt(self, recall: list[dict[str, Any]]) -> str:
        """Build a context string from recall items."""
        if not recall:
            return ""
        lines = ["## 相关记忆\n"]
        for item in recall[-8:]:
            role = item.get("metadata", {}).get("role", "system")
            content = item.get("content", "")[:300]
            lines.append(f"[{role}] {content}")
        lines.append("")
        return "\n".join(lines)

    # ── Goal tracking ─────────────────────────────────────────────────

    def _update_goals(self, user_text: str, assistant_text: str) -> bool:
        """Update active goals based on new conversation exchange."""
        updated = False
        norm = user_text.lower()
        for goal in self._active_goals:
            if any(kw in norm for kw in goal.get("keywords", [])):
                goal["interactions"] = goal.get("interactions", 0) + 1
                updated = True
        return updated

    async def _goal_check_loop(self) -> None:
        """Periodically check goal progress."""
        while self._running:
            await asyncio.sleep(self.config.goal_check_interval_seconds)
            if not self._active_goals:
                self._load_goals()
            self.logger.debug("goal check done, %d active goals", len(self._active_goals))

    def _load_goals(self) -> None:
        """Load active goals from memory or defaults."""
        stored = self.memory.search("goal:", limit=10, node_types=["goal"])
        if stored:
            self._active_goals = [s["metadata"] for s in stored]
        else:
            self._active_goals = []

    # ── Memory maintenance ────────────────────────────────────────────

    async def _memory_promotion_loop(self) -> None:
        """Periodically promote important nodes and prune old ones."""
        while self._running:
            await asyncio.sleep(self.config.memory_promotion_interval_seconds)
            try:
                self._promote_memory()
                pruned = self.memory.prune(keep_count=self.config.prune_threshold)
                if pruned > 0:
                    self.logger.info("memory pruned %d nodes", pruned)
            except Exception as exc:
                self.logger.warning("memory promotion failed: %s", exc)

    def _promote_memory(self) -> None:
        """Mark conversation nodes that get referenced often as important."""
        recent = self.memory.list_recent(limit=100, node_types=["conversation"])
        for node in recent:
            meta = node.get("metadata", {})
            interactions = meta.get("interactions", 0)
            if interactions > 3:
                self.memory.update_node(
                    node["id"],
                    node_type="important",
                    metadata={**meta, "promoted": True},
                )

    # ── Status ────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "turn_count": self._turn_count,
            "session_seconds": round(time.time() - self._session_started_at, 1),
            "idle_seconds": round(time.time() - self._last_activity_at, 1),
            "active_goals": len(self._active_goals),
            "memory_count": self.memory.count(),
            "tools_registered": len(self.tools),
            "tool_names": sorted(self.tools),
        }

    # ── Utilities ─────────────────────────────────────────────────────

    def register_tool(
        self,
        name: str,
        fn: Any,
        *,
        description: str | None = None,
        category: str = "general",
        input_schema: dict[str, Any] | None = None,
    ) -> None:
        self.tools[name] = fn
        doc = description
        if doc is None:
            doc = (getattr(fn, "__doc__", "") or "").strip().split("\n")[0]
        self.tool_specs[name] = ToolSpec(
            name=name,
            description=doc or "",
            category=category,
            input_schema=input_schema or {},
        )

    @staticmethod
    def _make_logger() -> Any:
        import logging
        return logging.getLogger("agent_loop")
