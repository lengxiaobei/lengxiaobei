from backend.autonomy.agent_loop import AgentLoop
from backend.autonomy.tools import register_all


class _Memory:
    pass


def test_agent_loop_parses_xml_tool_call_format():
    loop = AgentLoop(memory=_Memory(), tools={})

    calls = loop._parse_tool_calls(
        """
        <tool_call>
        <tool_name>code_search</tool_name>
        <args>{"pattern": "SkillLoader"}</args>
        </tool_call>
        <tool_call>
        <tool_name>code_search</tool_name>
        <args>{"pattern": "web_search"}</args>
        </tool_call>
        """
    )

    assert calls == [
        {"name": "code_search", "args": {"pattern": "SkillLoader"}},
        {"name": "code_search", "args": {"pattern": "web_search"}},
    ]


def test_agent_loop_strips_all_tool_call_formats():
    loop = AgentLoop(memory=_Memory(), tools={})

    text = loop._strip_tool_tags(
        """
        before
        <tool name="code_search">{"pattern":"A"}</tool>
        <tool_call>
        <tool_name>code_search</tool_name>
        <args>{"pattern": "B"}</args>
        </tool_call>
        <tool_call><function=shell_exec><parameter=command>echo bad</parameter></function></tool_call>
        after
        """
    )

    assert "tool_call" not in text
    assert "<tool" not in text
    assert "before" in text
    assert "after" in text


def test_agent_loop_registers_code_quality_tool():
    loop = AgentLoop(memory=_Memory(), tools={})

    register_all(loop)

    assert "code_quality" in loop.tools


def test_agent_loop_prompt_requires_diagnostics_for_repair_requests():
    loop = AgentLoop(memory=_Memory(), tools={})

    prompt = loop._build_system_prompt([])

    assert "修复类请求的硬要求" in prompt
    assert "code_quality" in prompt
    assert "不要只解释原因" in prompt
