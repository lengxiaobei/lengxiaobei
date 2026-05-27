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
import inspect
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from backend.memory.sqlite_backend import SQLiteMemoryBackend
from backend.config import get_settings


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
class TurnResult:
    """Result of a single agent loop run (may involve multiple tool calls)."""

    reply: str
    tool_calls: list[dict[str, Any]]
    recall_count: int
    goals_updated: bool
    elapsed_ms: float
    iterations: int = 0


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
        tools: dict[str, Any] | None = None,
        llm_completer: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        self.memory = memory or SQLiteMemoryBackend()
        self.config = config or AgentConfig()
        self.tools = tools or {}
        self.llm_completer = llm_completer
        self.logger = logger or self._make_logger()

        # Runtime state
        self._turn_count: int = 0
        self._session_started_at: float = time.time()
        self._last_activity_at: float = time.time()
        self._active_goals: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

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
        """Process one user message through the iterative agent loop.

        This is the core change: instead of plan-once-call-once, we loop:
            LLM generates text (may include <tool> tags)
            → parse tool calls
            → execute tools
            → append results to conversation
            → feed back to LLM
            → repeat until no more tool calls or max rounds reached
        """
        started = time.time()
        self._last_activity_at = time.time()
        self._turn_count += 1

        # 1. Write user message to memory
        self.memory.add_node(
            content=text,
            node_type="conversation",
            metadata={"role": "user", "channel": channel, "turn": self._turn_count},
            summary=text[:120],
        )

        # 2. Recall relevant context
        recall = self._recall(text)

        # 3. Build initial system prompt with tool descriptions
        system_prompt = self._build_system_prompt(recall)

        # 4. Iterative tool-calling loop
        all_tool_calls: list[dict[str, Any]] = []
        conversation: list[dict[str, str]] = [
            {"role": "user", "content": text},
        ]
        final_reply = ""
        iterations = 0

        for round_num in range(self.config.max_tool_rounds):
            iterations = round_num + 1

            # Call LLM with current conversation
            llm_response = await self._call_llm(conversation, system_prompt)

            if not llm_response:
                final_reply = "模型服务暂时不可用，请稍后再试。"
                break

            # Parse tool calls from LLM response
            tool_calls = self._parse_tool_calls(llm_response)

            if not tool_calls:
                # No more tool calls — LLM is done, this is the final reply
                final_reply = self._strip_tool_tags(llm_response)
                break

            # Execute tool calls and collect results
            tool_results_text = ""
            for tc in tool_calls:
                all_tool_calls.append(tc)
                result = await self._execute_tool(tc["name"], tc["args"])
                result_text = json.dumps(result, ensure_ascii=False, default=str)
                # Truncate very long results to avoid context overflow
                if len(result_text) > 4000:
                    result_text = result_text[:4000] + "\n... (truncated)"
                tool_results_text += TOOL_RESULT_TEMPLATE.format(
                    name=tc["name"], result=result_text
                ) + "\n"

            # Feed results back into conversation for next LLM call
            conversation.append({"role": "assistant", "content": llm_response})
            conversation.append({"role": "user", "content": tool_results_text})

        else:
            # Max rounds reached
            final_reply = self._strip_tool_tags(llm_response) if llm_response else "达到最大工具调用轮次，请简化请求。"

        # 5. Write assistant reply to memory
        self.memory.add_node(
            content=final_reply,
            node_type="conversation",
            metadata={"role": "assistant", "channel": channel, "turn": self._turn_count,
                      "tool_calls": all_tool_calls, "iterations": iterations},
            summary=final_reply[:120],
        )

        # 6. Update goals
        goals_updated = self._update_goals(text, final_reply)

        elapsed_ms = (time.time() - started) * 1000

        return TurnResult(
            reply=final_reply,
            tool_calls=all_tool_calls,
            recall_count=len(recall),
            goals_updated=goals_updated,
            elapsed_ms=elapsed_ms,
            iterations=iterations,
        )

    # ── System prompt with tool descriptions ─────────────────────────

    def _build_system_prompt(self, recall: list[dict[str, Any]]) -> str:
        """Build system prompt including tool documentation and recalled memory."""
        tool_docs = self._tool_descriptions()
        recall_text = self._build_recall_prompt(recall)

        return (
            "你是冷小北，运行在 LengXiaobei 本地优先智能体框架中。\n"
            "你拥有长期记忆，可以读写项目文件，执行命令，搜索代码，修改源码。\n\n"
            "## 可用工具\n\n"
            "你可以通过以下格式调用工具：\n\n"
            '<tool name="工具名">\n'
            "参数 JSON\n"
            "</tool>\n\n"
            f"{tool_docs}\n\n"
            "## 工作原则\n\n"
            "1. 先读后改：修改文件前先读取理解上下文\n"
            "2. 精确编辑：用 filesystem_edit 做精确替换，不要全文覆盖\n"
            "3. 验证结果：修改后运行编译检查或测试\n"
            "4. 失败修复：如果验证失败，分析错误信息并修复\n"
            "5. 诚实边界：不能读写 .env 文件，不能访问项目外路径\n\n"
            f"{recall_text}\n"
            "回答要简洁、直接、有主见。中文优先。"
        )

    def _tool_descriptions(self) -> str:
        """Generate tool documentation for the system prompt."""
        docs = []
        for name in sorted(self.tools):
            # Try to get docstring from the tool function
            fn = self.tools[name]
            doc = (fn.__doc__ or "").strip().split("\n")[0]
            if doc:
                docs.append(f"- **{name}**: {doc}")
            else:
                docs.append(f"- **{name}**")
        return "\n".join(docs)

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
        """Call the configured LLM with conversation history."""
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
            return ""

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

    def register_tool(self, name: str, fn: Any) -> None:
        self.tools[name] = fn

    @staticmethod
    def _make_logger() -> Any:
        import logging
        return logging.getLogger("agent_loop")
