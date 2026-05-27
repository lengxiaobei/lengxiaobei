"""Task planner and conversation commander.

参考来源：
- OpenClaw：Gateway 将多渠道消息交给 Commander，Commander 规划再交给 Dispatcher。
- OpenHuman：规划前先检索长期记忆，把记忆树作为上下文血脉。
- Hermes：把成功/失败轨迹写入记忆，供后续 reflector/skill_gen 生成技能。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from backend.config import PROJECT_ROOT, get_settings
from backend.core.llm.ollama import chat as ollama_chat
from backend.core.llm import claude_adapter


@dataclass
class TaskPlan:
    """轻量任务计划，参考 OpenClaw agent plan schema。"""

    intent: str
    tool: str | None
    args: dict[str, Any]
    reason: str


class Commander:
    """把用户输入翻译成计划、工具调用和最终回复。"""

    def __init__(self, dispatcher: Any, memory: Any, logger: Any, capability_registry: Any | None = None, user_profile: Any | None = None, agent_loop: Any | None = None):
        self.dispatcher = dispatcher
        self.memory = memory
        self.logger = logger
        self.capability_registry = capability_registry
        self.user_profile = user_profile
        self.agent_loop = agent_loop

    async def handle_message(self, text: str, channel: str = "web") -> dict[str, Any]:
        """处理单轮消息。

        局部参考：OpenHuman 的"对话即记忆节点"；Hermes 的"执行轨迹可回放"。
        """
        self.memory.add_node(
            content=text,
            node_type="conversation",
            metadata={"role": "user", "channel": channel},
            summary=text[:120],
        )
        recall = self._recall_context(text)
        plan = self._plan(text)
        observation = None
        settings = get_settings()

        # Agent Loop path — multi-turn tool-calling for complex requests
        # This is LengXiaobei's OWN ability: read → plan → edit → verify → fix
        # Works with ANY configured LLM (Ollama, token-plan, anthropic, etc.)
        if self._should_use_agent_loop(plan, settings):
            result = await self._agent_loop_reply(text, channel)
            return result

        if plan.tool:
            observation = await self.dispatcher.dispatch(plan.tool, plan.args)
            reply = self._summarize_tool_result(text, observation)
        elif plan.intent == "self_capability":
            reply = self._self_capability_reply()
        elif plan.intent == "ui_optimization":
            reply = self._ui_optimization_reply()
        elif plan.intent == "reference_gap":
            reply = self._reference_gap_reply()
        elif plan.intent == "model_info":
            reply = self._model_info_reply()
        elif plan.intent == "gateway_restart":
            reply = self._gateway_restart_reply()
        elif plan.intent == "code_modification":
            reply = self._code_modification_reply(text, observation)
        else:
            system = self._system_prompt(recall)
            reply = await ollama_chat(text, system=system)
        reply = self._sanitize_assistant_reply(reply, text)

        self.memory.add_node(
            content=reply,
            node_type="conversation",
            metadata={"role": "assistant", "channel": channel, "intent": plan.intent},
            summary=reply[:120],
        )
        return {"text": reply, "plan": asdict(plan), "observation": observation, "recall": recall}

    # ------------------------------------------------------------------
    # Planner helpers — normalized / compact forms computed once in _plan
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Declarative intent routing — replaces scattered _is_* methods
    # ------------------------------------------------------------------

    # (intent_name, tool_or_None, reason_template, check_fn)
    # check_fn(norm: str, compact: str) -> bool
    _INTENT_TABLE: list[tuple[str, str | None, str, Any]] = []  # populated below

    def _plan(self, text: str) -> TaskPlan:
        """规则优先的轻量规划器。

        局部参考：OpenClaw 先用确定性 routing 处理系统/工具类请求，复杂任务再交给 LLM。
        """
        norm, compact = _normalize(text)

        # Check declarative intent table first
        for intent, tool, reason, check_fn in self._INTENT_TABLE:
            if check_fn(compact, norm):
                return TaskPlan(intent, tool, {}, reason)

        # Code modification intent
        if self._is_code_modification_request(compact, norm):
            return TaskPlan("code_modification", "code_engineer", {"task": text}, "用户要求修改项目源码")

        # Compound intents that need extra args
        if self._is_controlled_agent_assignment(compact, norm):
            return TaskPlan("chat", None, {}, "用户提到参考系统；按冷小北原生能力交给 AgentLoop 处理")

        # Keyword-based fallback
        if "状态" in text or "status" in norm or "健康" in text:
            return TaskPlan("system_status", "system_status", {}, "用户询问运行状态")
        if "搜索记忆" in text or "memory" in norm or "记忆" in text:
            return TaskPlan("memory_search", "memory_search", {"query": text, "limit": 5}, "需要从长期记忆检索")
        if "反思" in text or "reflect" in norm:
            return TaskPlan("reflect", "reflect", {"topic": text}, "触发冷小北原生反思")
        if "技能" in text or "skill" in norm:
            return TaskPlan("skill_list", "skill_list", {}, "查看待审核/可用技能")
        return TaskPlan("chat", None, {}, "普通对话，由配置的 LLM 回复")

    def _is_model_question(self, compact: str, norm: str) -> bool:
        return (
            "什么模型" in compact
            or "哪个模型" in compact
            or "用的模型" in compact
            or "你用的什么模型" in compact
            or "what model" in norm
            or "which model" in norm
        )

    def _is_local_agent_request(self, compact: str, norm: str) -> bool:
        mentions_agent = "agent" in compact or "智能体" in compact or "代理" in compact
        asks_local = "本地" in compact or "local" in norm
        asks_connect = (
            "接入" in compact
            or "连接" in compact
            or "调用" in compact
            or "所有" in compact
            or "list" in norm
            or "connect" in norm
        )
        return mentions_agent and (asks_local or asks_connect)

    def _is_gateway_restart_request(self, compact: str, norm: str) -> bool:
        mentions_gateway = "网关" in compact or "gateway" in norm
        asks_restart = any(word in compact for word in ("重启", "重新启动", "restart", "reload"))
        return mentions_gateway and asks_restart

    def _is_reference_agent_connect_request(self, compact: str, norm: str) -> bool:
        mentions_reference = any(name in compact for name in ("openclaw", "hermes", "openhuman"))
        asks_connect = any(word in compact for word in ("接入", "连接", "控制", "分配任务", "派任务")) or "assign" in norm
        return mentions_reference and asks_connect

    def _is_controlled_agent_assignment(self, compact: str, norm: str) -> bool:
        mentions_reference = any(name in compact for name in ("openclaw", "hermes", "openhuman"))
        asks_assign = any(word in compact for word in ("让", "给", "派", "分配", "交给", "控制")) or "assign" in norm
        return mentions_reference and asks_assign and not any(word in compact for word in ("接入", "连接"))

    def _controlled_agent_target(self, compact: str) -> str:
        if "openclaw" in compact:
            return "openclaw"
        if "hermes" in compact:
            return "hermes"
        if "openhuman" in compact:
            return "openhuman"
        return "auto"

    def _is_code_modification_request(self, compact: str, norm: str) -> bool:
        """Detect requests to modify project source code."""
        # Explicit code engineering requests (strongest signal)
        explicit = any(kw in compact for kw in {
            "帮我改", "帮我修", "帮我写", "帮我添加", "帮我删", "帮我重构",
            "改一下", "修一下", "写一下", "添加一下",
            "改这个", "修这个", "写这个",
        })
        if explicit:
            return True

        # Keywords indicating code changes
        code_actions = {
            "改", "修改", "修复", "fix", "patch", "重构", "refactor",
            "优化", "optimize", "改进", "improve",
            "添加", "add", "增加", "append", "插入", "insert",
            "删除", "remove", "删掉", "去掉",
            "更新", "update", "升级", "upgrade",
            "实现", "implement", "写", "write",
        }
        has_action = any(kw in compact for kw in code_actions)

        # Code-related nouns or file paths
        code_targets = {
            "代码", "源码", "程序", "script",
            "文件", "file", ".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".md",
            "函数", "function", "fn",
            "类", "class",
            "方法", "method",
            "module", "模块", "mod",
            "组件", "component",
            "页面", "page",
            "路由", "route",
            "接口", "api", "endpoint",
            "配置", "config",
            "bug", "错误", "error", "问题", "issue",
            "测试", "test",
        }
        has_target = any(kw in compact for kw in code_targets)

        return has_action and has_target

    # ------------------------------------------------------------------
    # Recall / prompt helpers
    # ------------------------------------------------------------------

    def _recall_context(self, text: str) -> list[dict[str, Any]]:
        """Blend semantic-ish search with recent turns so pronouns keep their anchor."""
        candidates: list[dict[str, Any]] = []
        if text:
            candidates.extend(self.memory.search(text, limit=3))
        if hasattr(self.memory, "list_recent"):
            candidates.extend(self.memory.list_recent(limit=8))

        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in candidates:
            item_id = str(item.get("id") or "")
            if item_id in seen:
                continue
            seen.add(item_id)
            result.append(item)
            if len(result) >= 8:
                break
        return result

    def _is_self_capability_question(self, compact: str, norm: str) -> bool:
        return (
            "修改自己的源码" in compact
            or "改自己的源码" in compact
            or "修改你自己的源码" in compact
            or "改你自己的源码" in compact
            or "自我修改" in compact
            or "自我进化" in compact
            or "self modify" in norm
            or "modify your own source" in norm
        )

    def _is_ui_optimization_request(self, compact: str, norm: str) -> bool:
        asks_optimize = "优化" in compact or "改进" in compact or "optimize" in norm or "improve" in norm
        mentions_ui = (
            "ui" in compact
            or "界面" in compact
            or "页面" in compact
            or "聊天" in compact
            or "对话" in compact
            or "他" in compact
            or "它" in compact
            or "这个" in compact
        )
        return asks_optimize and mentions_ui

    def _is_reference_gap_question(self, compact: str, norm: str) -> bool:
        mentions_reference = (
            "openclaw" in compact
            or "hermes" in compact
            or "openhuman" in compact
        )
        asks_gap = (
            "哪些功能" in compact
            or "还不具备" in compact
            or "缺什么" in compact
            or "差距" in compact
            or "gap" in norm
            or "missing" in norm
        )
        return mentions_reference and asks_gap

    # ------------------------------------------------------------------
    # Static replies
    # ------------------------------------------------------------------

    def _ui_optimization_reply(self) -> str:
        return (
            "明白，你说的是当前聊天 UI。相关源码在 frontend/src/pages/ChatPage.tsx、"
            "frontend/src/components/Chat/MessageList.tsx、frontend/src/components/Chat/InputArea.tsx、"
            "frontend/src/stores/chatStore.ts 和 frontend/src/styles.css。"
            "我会优先优化这些点：消息气泡层次、自动滚动、多行输入、发送状态、快捷任务和空状态提示。"
            "当前冷小北运行时还不能直接写源码；如果由 Codex 开发代理执行，就可以直接修改这些文件、运行检查并重启前端。"
        )

    def _reference_gap_reply(self) -> str:
        return (
            "对标 OpenClaw、Hermes、OpenHuman 的能力类型，我现在是一个本地优先的骨架实现。"
            "它们只作为参照，目标是把能力长在冷小北自己身上，不是接入或遥控它们。\n\n"
            "通道与工具方向还缺：真实多渠道生产级接入、完整 Channel 生命周期管理、复杂任务规划、"
            "可写/可执行工具沙箱、权限审批流、工具市场和更细的 trace 可视化。目前 Telegram、WhatsApp、Slack、"
            "Playwright Browser 都是可选适配边界，运行时默认只开放读文件和只读 Shell。\n\n"
            "记忆连续性方向还缺：大规模 Sync Connectors 的真实授权同步、稳定的增量同步和冲突处理、"
            "更成熟的 MemoryTree 人工编辑体验、实体抽取、时间线、知识图谱推理和长期画像演化。现在已有 SQLite 记忆树、"
            "VectorStore fallback、GraphStore 边界和同步管理框架，但深度还需要补。\n\n"
            "反思与技能方向还缺：从执行轨迹自动沉淀技能后的高质量验证、自动评估集、失败归因、技能版本管理、"
            "回滚机制、多模型评审和真正闭环的自我改进。目前已有 SkillGen、SkillStore、Reflector、Evaluator，"
            "新技能默认 pending，需要人工审核。\n\n"
            "最关键的下一步，我建议按顺序补三件事：1. 审核型 patch/write 工具；2. 技能验证与回滚；"
            "3. 真实同步连接器和记忆图谱可视化。这样冷小北会从'能记、能反思'进一步走向'能安全改、能验证、能积累'。"
        )

    def _self_capability_reply(self) -> str:
        return (
            "可以，现在我已经具备项目内源码修改工具，但要分层说清楚：我不能修改云端模型权重，也不能越过项目边界。"
            "在 lengxiaobei 这个本地项目里，我已经能写长期记忆、反思执行轨迹、生成 pending 技能并等待审核；"
            "这些属于冷小北自己的原生自我进化。"
            "源码级修改方面，运行时已经开放 filesystem_write、filesystem_append、filesystem_delete 和 shell_exec，"
            "可以在项目根目录内改文件、运行检查、把执行轨迹写入 trace。"
            "我仍然会拒绝读写 .env 这类本地密钥文件，也不能直接改项目外路径。"
        )

    def _model_info_reply(self) -> str:
        settings = get_settings()
        provider = settings.llm_provider.lower().replace("_", "-")
        adapter_status = (
            "OpenAI-compatible 云端适配器已启用"
            if provider in {"openai", "openai-compatible", "token-plan"}
            else "本地 Ollama 适配器已启用"
            if provider == "ollama"
            else "该 provider 目前还没有专用适配器"
        )
        return (
            f"我现在按 LengXiaobei / YourAgent 新架构运行。"
            f"配置的 LLM provider 是 {settings.llm_provider}，模型是 {settings.llm_model}，"
            f"base URL 是 {settings.llm_base_url}。{adapter_status}。"
        )

    def _code_modification_reply(self, text: str, observation: dict[str, Any] | None) -> str:
        """Summarize the result of a code engineering task."""
        if not observation or not observation.get("ok"):
            error = (observation or {}).get("summary", "代码修改任务未能完成")
            return f"代码修改任务遇到问题：{error}。我会把这次尝试记录到记忆里，供后续分析。"
        iterations = observation.get("iterations", [])
        if not iterations:
            return "代码修改任务已提交，但还没有返回详细结果。"
        last = iterations[-1]
        if last.get("ok"):
            steps = len(last.get("plan", []))
            return (
                f"代码修改已完成，共执行 {len(iterations)} 轮迭代，"
                f"最后一步包含 {steps} 个操作。"
                f"验证结果：通过。"
            )
        return (
            f"代码修改尝试了 {len(iterations)} 轮仍未完全成功。"
            f"最后验证错误：{last.get('verification', {}).get('error', 'unknown')}"
        )

    def _gateway_restart_reply(self) -> str:
        return (
            "我不能从正在运行的 Web 网关进程里直接杀掉并重启自己，否则这次请求会被中断。"
            f"正确的本地项目路径是 {PROJECT_ROOT}；"
            "由外部终端或 Codex 执行 `./scripts/start_backend.sh` 可以重启后端网关。"
        )

    # ------------------------------------------------------------------
    # Claude Tool Use helpers
    # ------------------------------------------------------------------

    def _should_use_claude_tools(self, plan: TaskPlan, settings: Any) -> bool:
        """Decide whether to route through Claude's native Tool Use."""
        if not getattr(settings, "llm_claude_enable_tools", False):
            return False
        provider = (settings.llm_provider or "").lower()
        if "anthropic" not in provider:
            return False
        # Only use Tool Use for open-ended chat that would otherwise hit the LLM
        if plan.intent != "chat":
            return False
        return True

    async def _claude_tool_use_reply(self, text: str, recall: list[dict[str, Any]], settings: Any) -> str:
        """Route the request through Claude with native Tool Use."""
        system = self._system_prompt(recall)
        tools = claude_adapter.get_tool_schemas()

        async def _tool_executor(name: str, args: dict[str, Any]) -> Any:
            result = await self.dispatcher.dispatch(name, args)
            return result

        try:
            result = await claude_adapter.chat_with_tools(
                prompt=text,
                system=system,
                tools=tools,
                tool_executor=_tool_executor,
                enable_caching=getattr(settings, "llm_claude_enable_caching", False),
                thinking_budget=getattr(settings, "llm_claude_thinking_budget", 0) or None,
            )
            return result.content
        except Exception as exc:
            self.logger.warning("Claude Tool Use failed: %s", exc)
            # Fallback to regular ollama chat
            return await ollama_chat(text, system=system)

    def _should_use_agent_loop(self, plan: TaskPlan, settings: Any) -> bool:
        """Decide whether to route through the multi-turn Agent Loop.

        Use Agent Loop for any request where LengXiaobei needs to reason
        about code or take multiple actions — not just for Claude.
        """
        if self.agent_loop is None:
            return False
        # Code modification and open-ended chat both benefit from multi-turn
        if plan.intent in ("code_modification", "chat"):
            return True
        return False

    async def _agent_loop_reply(self, text: str, channel: str) -> dict[str, Any]:
        """Route through the Agent Loop for multi-turn tool-calling."""
        try:
            result = await self.agent_loop.handle(text, channel=channel)
            return {
                "text": result.reply,
                "plan": {"intent": "agent_loop", "tool": None, "args": {}, "reason": "multi-turn agent loop"},
                "observation": None,
                "recall": [],
                "tool_calls": result.tool_calls,
                "iterations": result.iterations,
                "elapsed_ms": result.elapsed_ms,
            }
        except Exception as exc:
            self.logger.warning("Agent Loop failed, falling back to simple chat: %s", exc)
            # Fallback to simple LLM chat
            system = self._system_prompt(self._recall_context(text))
            reply = await ollama_chat(text, system=system)
            return {"text": reply, "plan": {"intent": "chat_fallback", "tool": None, "args": {}, "reason": "agent loop failed"}, "observation": None, "recall": []}

    # ------------------------------------------------------------------
    # Prompt / sanitize / summarize
    # ------------------------------------------------------------------

    def _system_prompt(self, recall: list[dict[str, Any]]) -> str:
        """把 OpenHuman 风格记忆召回 + Hermes 双层记忆注入系统提示。"""
        safe_recall = [item for item in recall if self._is_safe_recall(item)]
        base = (
            "你是冷小北，运行在 lengxiaobei 本地优先智能体框架中。"
            "你不是普通无状态聊天模型：你可以使用项目提供的长期记忆、工具调度、反思、技能生成和审核机制。"
            "能力边界要诚实：你不能修改模型权重，不能读写项目外路径；当前运行时已经暴露项目内文件读写、删除和 shell_exec，"
            "可以修改 lengxiaobei 仓库源码并运行检查。"
            "当用户问你是否能修改自己源码时，要说明这些分层边界，不要说自己完全不能记忆或进化。"
            "当前聊天 UI 的源码在 frontend/src/pages/ChatPage.tsx、frontend/src/components/Chat/MessageList.tsx、"
            "frontend/src/components/Chat/InputArea.tsx、frontend/src/stores/chatStore.ts 和 frontend/src/styles.css；"
            "如果用户说'优化他/它/这个界面'，通常指这个聊天 UI。"
        )
        if safe_recall:
            snippets = "\n".join(f"- {item.get('summary') or item.get('content', '')[:160]}" for item in safe_recall)
            base += "\n相关记忆：\n" + snippets

        # Inject Hermes-style user profile + memory notes
        if self.user_profile:
            try:
                memory_block = self.user_profile.inject_into_prompt()
                if memory_block:
                    base += "\n\n" + memory_block
            except Exception:
                pass  # Non-critical

        return base

    def _is_safe_recall(self, item: dict[str, Any]) -> bool:
        """Avoid feeding previous adapter failures back into the next model prompt."""
        text = f"{item.get('summary') or ''}\n{item.get('content') or ''}"
        blocked = (
            "系统上下文：",
            "当前 LLM 不可用",
            "当前本地 Ollama 不可用",
            "No module named 'src'",
            "urlopen error",
            "Connection refused",
            "本地兜底",
            "本地模型暂时",
            "模型服务暂时",
            "没有连上模型",
            "没有连上本地模型",
            "如果本地 Ollama",
            "无法修改自己的源码",
            "无法自我升级",
            "不会\"记住\"",
            "静态的语言模型",
            "提示词层面的设定",
            "界面源码的位置",
            "UI代码在哪个目录",
        )
        return not any(marker in text for marker in blocked)

    def _summarize_capability_result(self, result: dict[str, Any]) -> str:
        summary = str(result.get("summary") or "任务已处理。")
        actions = [str(item) for item in (result.get("next_actions") or []) if item]
        if not actions:
            return summary
        return summary + "\n\n建议下一步：\n" + "\n".join(f"- {item}" for item in actions[:4])

    def _summarize_tool_result(self, text: str, observation: dict[str, Any]) -> str:
        """Turn tool observations into chat-safe, human-readable replies."""
        if not observation.get("ok"):
            return f"执行失败：{observation.get('error', 'unknown error')}"
        if observation.get("tool") == "local_agent_list":
            agents = observation.get("result") or []
            if not agents:
                return (
                    "我已经打开本地 agent 接入层，但还没在默认目录里发现 agent。"
                    "可以通过 LOCAL_AGENT_ROOTS 或 data/local_agents.json 显式配置。"
                )
            lines = []
            for agent in agents[:12]:
                callable_label = "可直接调用" if agent.get("callable") else "已发现，待配置命令"
                markers = ", ".join(agent.get("markers") or [])
                lines.append(f"- {agent.get('name')} [{agent.get('id')}]：{callable_label}；{markers}")
            suffix = "" if len(agents) <= 12 else f"\n另有 {len(agents) - 12} 个未展开。"
            return "已接入本地 agent 发现层，当前发现：\n" + "\n".join(lines) + suffix
        if observation.get("tool") == "controlled_agent_list":
            agents = observation.get("result") or []
            lines = []
            for agent in agents:
                callable_label = "可命令执行" if agent.get("callable") else "通过 inbox 投递"
                lines.append(f"- {agent.get('name')} [{agent.get('id')}]：{callable_label}；{agent.get('description')}")
            return "当前保留的是兼容发现层，不是冷小北的能力目标；原生能力应优先落在通道、反思技能和记忆连续性里：\n" + "\n".join(lines)
        if observation.get("tool") == "controlled_agent_assign":
            result = observation.get("result") or {}
            target = (result.get("target") or {}).get("name", "unknown")
            direct_result = result.get("result") or {}
            if result.get("ok"):
                return f"已把任务分配给 {target}，正在等待它回传处理结果。"
            if (result.get("assignment") or {}).get("ok"):
                return f"已把任务投递给 {target}。它会进入本地任务队列继续处理，我会保留这次巡检记录。"
            error = direct_result.get("error") or "任务投递没有完成"
            return f"{target} 暂时没有接住任务：{error}"
        if observation.get("tool") == "memory_search":
            results = observation.get("result") or []
            if not results:
                return "我查了长期记忆，没有找到相关内容。"
            lines = []
            for item in results[:5]:
                summary = item.get("summary") or item.get("content") or ""
                node_type = item.get("type") or item.get("node_type") or "memory"
                lines.append(f"- [{node_type}] {str(summary).strip()[:180]}")
            return "我查到这些相关记忆：\n" + "\n".join(lines)
        result = observation.get("result")
        if isinstance(result, str) and result.strip():
            return f"已处理：{text}\n\n结果：{result}"
        return f"已处理：{text}"

    def _sanitize_assistant_reply(self, reply: str, user_text: str) -> str:
        """Prevent raw tool-call markup from leaking into the chat UI."""
        if not reply:
            return reply
        stripped = re.sub(r"<tool_call>.*?</tool_call>", "", reply, flags=re.DOTALL | re.IGNORECASE)
        stripped = re.sub(r"<function=[^>]+>.*?</function>", "", stripped, flags=re.DOTALL | re.IGNORECASE)
        stripped = re.sub(r"<parameter=[^>]+>.*?</parameter>", "", stripped, flags=re.DOTALL | re.IGNORECASE)
        if stripped.strip() == reply.strip():
            return reply
        cleaned = stripped.strip()
        if cleaned:
            return cleaned
        if self._is_gateway_restart_request(*_normalize(user_text)):
            return self._gateway_restart_reply()
        return "我刚才生成了内部工具调用格式，但这个聊天界面不能直接执行那种标记。请直接说明要执行的动作，我会走可用的系统工具。"


def _normalize(text: str) -> tuple[str, str]:
    """Return (lowercased, compact-without-whitespace-lowercased) for intent matching."""
    norm = text.lower()
    compact = "".join(norm.split())
    return norm, compact


# ── Declarative intent patterns ─────────────────────────────────────
# Each entry: (intent, tool_or_None, reason, check_fn(compact, norm) -> bool)
# Checked in order; first match wins.

def _check_self_capability(compact: str, norm: str) -> bool:
    return any(kw in compact for kw in (
        "修改自己的源码", "改自己的源码", "修改你自己的源码", "改你自己的源码",
        "自我修改", "自我进化",
    )) or "self modify" in norm or "modify your own source" in norm


def _check_ui_optimization(compact: str, norm: str) -> bool:
    asks = any(kw in compact for kw in ("优化", "改进")) or any(kw in norm for kw in ("optimize", "improve"))
    ui = any(kw in compact for kw in ("ui", "界面", "页面", "聊天", "对话", "他", "它", "这个"))
    return asks and ui


def _check_reference_gap(compact: str, norm: str) -> bool:
    ref = any(kw in compact for kw in ("openclaw", "hermes", "openhuman"))
    gap = any(kw in compact for kw in ("哪些功能", "还不具备", "缺什么", "差距")) or any(kw in norm for kw in ("gap", "missing"))
    return ref and gap


def _check_model_question(compact: str, norm: str) -> bool:
    return any(kw in compact for kw in ("什么模型", "哪个模型", "用的模型", "你用的什么模型")) or any(kw in norm for kw in ("what model", "which model"))


def _check_gateway_restart(compact: str, norm: str) -> bool:
    gw = "网关" in compact or "gateway" in norm
    restart = any(kw in compact for kw in ("重启", "重新启动", "restart", "reload"))
    return gw and restart


def _check_reference_agent_connect(compact: str, norm: str) -> bool:
    ref = any(kw in compact for kw in ("openclaw", "hermes", "openhuman"))
    connect = any(kw in compact for kw in ("接入", "连接", "控制", "分配任务", "派任务")) or "assign" in norm
    return False


def _check_local_agent(compact: str, norm: str) -> bool:
    agent = any(kw in compact for kw in ("agent", "智能体", "代理"))
    local = "本地" in compact or "local" in norm
    connect = any(kw in compact for kw in ("接入", "连接", "调用", "所有", "list", "connect"))
    return agent and (local or connect)


# Assign the intent table
Commander._INTENT_TABLE = [
    ("self_capability", None, "用户询问自我修改或自我进化边界", _check_self_capability),
    ("ui_optimization", None, "用户要求优化聊天 UI", _check_ui_optimization),
    ("reference_gap", None, "用户询问对标 OpenClaw/Hermes/OpenHuman 的能力差距", _check_reference_gap),
    ("model_info", None, "用户询问当前模型配置", _check_model_question),
    ("gateway_restart", None, "用户要求重启 lengxiaobei 后端网关", _check_gateway_restart),
    ("controlled_agents", "controlled_agent_list", "兼容发现层已停用；优先冷小北原生能力", _check_reference_agent_connect),
    ("local_agents", "local_agent_list", "用户希望接入或查看本地 agent", _check_local_agent),
]
