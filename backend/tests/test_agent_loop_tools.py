from backend.autonomy.agent_loop import AgentLoop


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
