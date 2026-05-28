from backend.core.commander import Commander
from backend.core.llm.ollama import local_fallback


class _Memory:
    def __init__(self):
        self.nodes = []

    def add_node(self, **kwargs):
        self.nodes.append(kwargs)

    def search(self, *args, **kwargs):
        return []

    def list_recent(self, *args, **kwargs):
        return []


class _AgentLoop:
    async def handle(self, text, channel="web"):
        class Result:
            reply = "agent loop handled"
            tool_calls = []
            iterations = 1
            elapsed_ms = 1
            run_id = ""

        return Result()


def test_system_prompt_filters_adapter_failure_memories():
    commander = Commander(dispatcher=None, memory=None, logger=None)

    prompt = commander._system_prompt(
        [
            {
                "summary": "系统上下文：旧的内部提示",
                "content": "当前 LLM 不可用，原因：No module named 'src'",
            },
            {
                "summary": "我还是在本地兜底模式运行中",
                "content": "模型服务暂时没有连上",
            },
            {"summary": "用户喜欢简洁回答", "content": "用户喜欢简洁回答"},
        ]
    )

    assert "用户喜欢简洁回答" in prompt
    assert "系统上下文：" not in prompt
    assert "No module named 'src'" not in prompt
    assert "本地兜底" not in prompt


def test_local_fallback_is_human_facing():
    reply = local_fallback("你好", reason="ollama unavailable")

    assert "冷小北" in reply
    assert "系统上下文" not in reply
    assert "Connection refused" not in reply


def test_self_capability_reply_is_project_specific():
    commander = Commander(dispatcher=None, memory=None, logger=None)

    plan = commander._plan("你能修改自己的源码吗")
    reply = commander._self_capability_reply()

    assert plan.intent == "self_capability"
    assert "长期记忆" in reply
    assert "pending 技能" in reply
    assert "filesystem_write" in reply
    assert "shell_exec" in reply
    assert "静态的语言模型" not in reply


def test_ui_optimization_request_resolves_project_files():
    commander = Commander(dispatcher=None, memory=None, logger=None)

    plan = commander._plan("我让你优化他")
    reply = commander._ui_optimization_reply()

    assert plan.intent == "ui_optimization"
    assert "当前聊天 UI" in reply
    assert "frontend/src/pages/ChatPage.tsx" in reply
    assert "Codex" in reply


def test_reference_gap_question_has_deterministic_answer():
    commander = Commander(dispatcher=None, memory=None, logger=None)

    plan = commander._plan("参照 OpenClaw、Hermes、OpenHuman，还有哪些功能不具备")
    reply = commander._reference_gap_reply()

    assert plan.intent == "reference_gap"
    assert "能力类型" in reply
    assert "不是接入或遥控它们" in reply
    assert "通道与工具方向还缺" in reply
    assert "记忆连续性方向还缺" in reply
    assert "反思与技能方向还缺" in reply
    assert "审核型 patch/write 工具" in reply


def test_reference_agent_connect_does_not_route_to_external_control():
    commander = Commander(dispatcher=None, memory=None, logger=None)

    plan = commander._plan("把我本地的 OpenClaw、Hermes、OpenHuman 接入 lengxiaobei")

    assert plan.intent == "chat"
    assert plan.tool is None


def test_reference_agent_assignment_stays_native():
    commander = Commander(dispatcher=None, memory=None, logger=None)

    plan = commander._plan("让 Hermes 反思最近失败的技能生成任务")

    assert plan.intent == "reflect"
    assert plan.tool == "reflect"


def test_reference_agent_message_uses_agent_loop():
    import asyncio

    commander = Commander(
        dispatcher=None,
        memory=_Memory(),
        logger=None,
        agent_loop=_AgentLoop(),
    )

    result = asyncio.run(commander.handle_message("让 Hermes 反思最近失败的技能生成任务"))

    assert result["text"] == "agent loop handled"
    assert result["plan"]["intent"] == "agent_loop"


def test_open_ended_tool_intents_use_agent_loop():
    import asyncio

    commander = Commander(
        dispatcher=None,
        memory=_Memory(),
        logger=None,
        agent_loop=_AgentLoop(),
    )

    for text in ("我让你优化他", "搜索记忆：联网能力", "反思最近一次失败", "看看现在有什么技能"):
        result = asyncio.run(commander.handle_message(text))
        assert result["text"] == "agent loop handled"
        assert result["plan"]["intent"] == "agent_loop"


def test_gateway_restart_request_is_deterministic():
    commander = Commander(dispatcher=None, memory=None, logger=None)

    plan = commander._plan("重启下网关")
    reply = commander._gateway_restart_reply()

    assert plan.intent == "gateway_restart"
    assert plan.tool is None
    assert "/Users/panhao/projects/lengxiaobei" in reply
    assert "/home/xpz" not in reply


def test_tool_call_markup_is_not_exposed():
    commander = Commander(dispatcher=None, memory=None, logger=None)

    reply = commander._sanitize_assistant_reply(
        '好的<tool_call><function=shell_exec><parameter=command>echo bad</parameter></function></tool_call>',
        "执行一下",
    )

    assert "<tool_call>" not in reply
    assert "shell_exec" not in reply


def test_memory_search_summary_does_not_expose_embeddings():
    commander = Commander(dispatcher=None, memory=None, logger=None)

    reply = commander._summarize_tool_result(
        "搜索记忆",
        {
            "ok": True,
            "tool": "memory_search",
            "result": [
                {
                    "type": "conversation",
                    "summary": "你的联网能力现在能用吗",
                    "embedding": [0.1, 0.2],
                    "vector_backend": "hash",
                }
            ],
        },
    )

    assert "你的联网能力现在能用吗" in reply
    assert "embedding" not in reply
    assert "vector_backend" not in reply
