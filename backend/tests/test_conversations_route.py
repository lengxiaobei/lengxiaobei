import asyncio

from backend.api.routes.conversations import create_message
from backend.api.schemas import ConversationInput


class _MemoryHooks:
    async def auto_recall(self, message: str):
        return [{"summary": "你好"}]

    def format_recall_context(self, results):
        return "[相关记忆]\n- [knowledge] 你好"


class _Commander:
    def __init__(self):
        self.seen = None

    async def handle_message(self, text: str, channel: str = "web"):
        self.seen = text
        return {"text": "ok"}


class _Runtime:
    def __init__(self):
        self.memory_hooks = _MemoryHooks()
        self.session_manager = None
        self.commander = _Commander()

    def touch_activity(self, source: str):
        self.source = source


def test_conversation_route_does_not_prepend_recall_context_to_user_message():
    rt = _Runtime()

    result = asyncio.run(
        create_message(ConversationInput(message="你的联网能力现在能用吗", channel="web"), rt=rt)
    )

    assert result["result"]["text"] == "ok"
    assert rt.commander.seen == "你的联网能力现在能用吗"
    assert "[相关记忆]" not in rt.commander.seen
