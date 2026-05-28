"""Fact extractor — extracts key facts from conversations to long-term memory.

参考来源：Hermes 的 memory hooks — 从对话中提取用户偏好、技术决策、
项目约定等关键事实，写入长期记忆避免遗忘。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class FactExtractor:
    """从对话中提取关键事实并写入长期记忆。"""

    def __init__(
        self,
        memory: Any,
        llm_completer: Callable[[str, str], Awaitable[str]] | None = None,
        extract_interval: int = 5,  # 每 N 轮对话提取一次
    ):
        self.memory = memory
        self.llm_completer = llm_completer
        self.extract_interval = extract_interval
        self._turn_count: int = 0
        self._extracted_count: int = 0

    async def maybe_extract(
        self,
        user_message: str,
        assistant_reply: str,
    ) -> list[dict[str, Any]]:
        """每 N 轮对话提取一次关键事实。返回提取的事实列表。"""
        self._turn_count += 1
        if self._turn_count % self.extract_interval != 0:
            return []

        if not self.llm_completer:
            return []

        facts = await self._extract_facts(user_message, assistant_reply)
        stored = []
        for fact in facts:
            try:
                node = self.memory.add_node(
                    content=fact["content"],
                    node_type="fact",
                    metadata={
                        "category": fact.get("category", "general"),
                        "source": "auto_extract",
                        "confidence": fact.get("confidence", 0.7),
                    },
                    summary=fact["content"][:120],
                )
                stored.append(node)
                self._extracted_count += 1
            except Exception as e:
                logger.warning("Failed to store fact: %s", e)

        if stored:
            logger.info("Extracted %d facts from conversation", len(stored))
        return stored

    async def _extract_facts(
        self,
        user_message: str,
        assistant_reply: str,
    ) -> list[dict[str, Any]]:
        """用 LLM 从对话中提取关键事实。"""
        prompt = (
            "从以下对话中提取值得长期记住的关键事实。包括：\n"
            "- 用户偏好（技术栈、工作习惯、沟通风格）\n"
            "- 技术决策（架构选择、工具选型、约定）\n"
            "- 项目约定（命名规范、目录结构、工作流）\n"
            "- 重要结论（问题根因、解决方案、经验教训）\n\n"
            "输出 JSON 数组，每个元素格式：\n"
            '{"content": "事实描述", "category": "preference|decision|convention|lesson", "confidence": 0.8}\n\n'
            "只提取有长期价值的事实，忽略一次性操作和临时状态。如果没有值得提取的事实，返回空数组 []\n\n"
            f"用户：{user_message[:500]}\n"
            f"助手：{assistant_reply[:500]}"
        )

        try:
            response = await self.llm_completer(
                prompt,
                "你是事实提取助手。只输出 JSON 数组，不要其他内容。"
            )
            # Parse JSON response
            import json
            # Try to find JSON array in response
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                facts = json.loads(response[start:end])
                if isinstance(facts, list):
                    return [f for f in facts if isinstance(f, dict) and f.get("content")]
        except Exception as e:
            logger.warning("Fact extraction LLM call failed: %s", e, exc_info=True)

        return []

    def stats(self) -> dict[str, Any]:
        return {
            "turn_count": self._turn_count,
            "extracted_count": self._extracted_count,
            "extract_interval": self.extract_interval,
        }
