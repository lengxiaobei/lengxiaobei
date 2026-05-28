"""Context compressor for long conversations.

参考来源：TokenJuice 风格上下文压缩 — 当对话历史超过 token 阈值时，
自动摘要旧消息，保留关键信息，减少 token 消耗。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class ContextCompressor:
    """对话上下文压缩器。

    当 conversation 超过 max_messages 时，将旧消息摘要化，
    保留最近 keep_recent 条原始消息。
    """

    def __init__(
        self,
        llm_completer: Callable[[str, str], Awaitable[str]] | None = None,
        max_messages: int = 20,
        keep_recent: int = 6,
        summary_max_tokens: int = 500,
    ):
        self.llm_completer = llm_completer
        self.max_messages = max_messages
        self.keep_recent = keep_recent
        self.summary_max_tokens = summary_max_tokens
        self._last_compression_at: float = 0
        self._compression_count: int = 0

    async def maybe_compress(
        self,
        conversation: list[dict[str, str]],
        system_context: str = "",
    ) -> list[dict[str, str]]:
        """如果对话超过阈值，压缩旧消息。返回新的 conversation。"""
        if len(conversation) <= self.max_messages:
            return conversation

        # Split: old messages to summarize + recent messages to keep
        split_point = len(conversation) - self.keep_recent
        old_messages = conversation[:split_point]
        recent_messages = conversation[split_point:]

        # Generate summary of old messages
        summary = await self._summarize_messages(old_messages, system_context)

        # Build compressed conversation
        compressed = []
        if summary:
            compressed.append({
                "role": "system",
                "content": f"[对话历史摘要]\n{summary}",
            })
        compressed.extend(recent_messages)

        self._last_compression_at = time.time()
        self._compression_count += 1

        logger.info(
            "Context compressed: %d messages → %d + summary (%d compressions total)",
            len(conversation), len(compressed), self._compression_count,
        )
        return compressed

    async def _summarize_messages(
        self,
        messages: list[dict[str, str]],
        system_context: str,
    ) -> str:
        """用 LLM 摘要一组消息。"""
        if not self.llm_completer:
            return self._fallback_summary(messages)

        # Build summarization prompt
        conversation_text = "\n".join(
            f"[{m.get('role', 'user')}] {m.get('content', '')[:300]}"
            for m in messages
        )

        prompt = (
            "请将以下对话历史压缩为简洁摘要，保留：\n"
            "1. 用户的核心需求和目标\n"
            "2. 已完成的关键操作\n"
            "3. 未解决的问题或待办\n"
            "4. 重要的技术决策和结论\n\n"
            "不要保留寒暄、确认、错误重试等噪声。输出纯文本摘要，不超过300字。\n\n"
            f"对话历史：\n{conversation_text}"
        )

        try:
            summary = await self.llm_completer(prompt, "你是一个对话摘要助手，输出简洁准确的摘要。")
            return summary[:self.summary_max_tokens] if summary else self._fallback_summary(messages)
        except Exception as e:
            logger.warning("LLM summarization failed, using fallback: %s", e)
            return self._fallback_summary(messages)

    def _fallback_summary(self, messages: list[dict[str, str]]) -> str:
        """不依赖 LLM 的简单摘要。"""
        user_msgs = [m for m in messages if m.get("role") == "user"]
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]

        lines = []
        if user_msgs:
            lines.append("用户主要请求：")
            for m in user_msgs[-3:]:
                content = m.get("content", "")[:100]
                lines.append(f"- {content}")
        if assistant_msgs:
            last = assistant_msgs[-1].get("content", "")[:200]
            lines.append(f"最后回复：{last}")
        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        return {
            "compression_count": self._compression_count,
            "last_compression_at": self._last_compression_at,
            "max_messages": self.max_messages,
            "keep_recent": self.keep_recent,
        }
