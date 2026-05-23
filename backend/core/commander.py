"""Task planner and conversation commander.

参考来源：
- OpenClaw：Gateway 将多渠道消息交给 Commander，Commander 规划再交给 Dispatcher。
- OpenHuman：规划前先检索长期记忆，把记忆树作为上下文血脉。
- Hermes：把成功/失败轨迹写入记忆，供后续 reflector/skill_gen 生成技能。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.config import get_settings
from backend.core.llm.ollama import chat as ollama_chat


@dataclass(slots=True)
class TaskPlan:
    """轻量任务计划，参考 OpenClaw agent plan schema。"""

    intent: str
    tool: str | None
    args: dict[str, Any]
    reason: str


class Commander:
    """把用户输入翻译成计划、工具调用和最终回复。"""

    def __init__(self, dispatcher: Any, memory: Any, logger: Any):
        self.dispatcher = dispatcher
        self.memory = memory
        self.logger = logger

    async def handle_message(self, text: str, channel: str = "web") -> dict[str, Any]:
        """处理单轮消息。

        局部参考：OpenHuman 的“对话即记忆节点”；Hermes 的“执行轨迹可回放”。
        """
        self.memory.add_node(
            content=text,
            node_type="conversation",
            metadata={"role": "user", "channel": channel},
            summary=text[:120],
        )
        recall = self.memory.search(text, limit=3) if text else []
        plan = self._plan(text)
        observation = None
        if plan.tool:
            observation = await self.dispatcher.dispatch(plan.tool, plan.args)
            reply = self._summarize_tool_result(text, observation)
        elif plan.intent == "model_info":
            reply = self._model_info_reply()
        else:
            system = self._system_prompt(recall)
            reply = ollama_chat(text, system=system)

        self.memory.add_node(
            content=reply,
            node_type="conversation",
            metadata={"role": "assistant", "channel": channel, "intent": plan.intent},
            summary=reply[:120],
        )
        return {"text": reply, "plan": asdict(plan), "observation": observation, "recall": recall}

    def _plan(self, text: str) -> TaskPlan:
        """规则优先的轻量规划器。

        局部参考：OpenClaw 先用确定性 routing 处理系统/工具类请求，复杂任务再交给 LLM。
        """
        normalized = text.lower()
        if self._is_model_question(text, normalized):
            return TaskPlan("model_info", None, {}, "用户询问当前模型配置")
        if "状态" in text or "status" in normalized or "健康" in text:
            return TaskPlan("system_status", "system_status", {}, "用户询问运行状态")
        if "搜索记忆" in text or "memory" in normalized or "记忆" in text:
            return TaskPlan("memory_search", "memory_search", {"query": text, "limit": 5}, "需要从长期记忆检索")
        if "反思" in text or "reflect" in normalized:
            return TaskPlan("reflect", "reflect", {"topic": text}, "触发 Hermes 风格反思")
        if "技能" in text or "skill" in normalized:
            return TaskPlan("skill_list", "skill_list", {}, "查看待审核/可用技能")
        return TaskPlan("chat", None, {}, "普通对话，由 LLM 或本地兜底回复")

    def _is_model_question(self, text: str, normalized: str) -> bool:
        compact = "".join(text.split())
        return (
            "什么模型" in compact
            or "哪个模型" in compact
            or "用的模型" in compact
            or "你用的什么模型" in compact
            or "what model" in normalized
            or "which model" in normalized
        )

    def _model_info_reply(self) -> str:
        settings = get_settings()
        return (
            f"我现在按 LengXiaobei / YourAgent 新架构运行。"
            f"配置的 LLM provider 是 {settings.llm_provider}，模型是 {settings.llm_model}，"
            f"base URL 是 {settings.llm_base_url}。"
            "如果本地 Ollama 或对应服务没有启动，我会使用本地确定性兜底回复，而不会再依赖旧的 src 模块。"
        )

    def _system_prompt(self, recall: list[dict[str, Any]]) -> str:
        """把 OpenHuman 风格记忆召回压缩进系统提示。"""
        if not recall:
            return "你是本地优先、可进化的 LengXiaobei/YourAgent 助手。"
        snippets = "\n".join(f"- {item.get('summary') or item.get('content', '')[:160]}" for item in recall)
        return "你是本地优先、可进化的 LengXiaobei/YourAgent 助手。相关记忆：\n" + snippets

    def _summarize_tool_result(self, text: str, observation: dict[str, Any]) -> str:
        """把 OpenClaw observation 转成人类可读回复。"""
        if not observation.get("ok"):
            return f"执行失败：{observation.get('error', 'unknown error')}"
        return f"已处理：{text}\n\n结果：{observation.get('result')}"
