import asyncio
from pathlib import Path

from backend.core.dispatcher import Dispatcher
from backend.evolution.reflector import Reflector
from backend.evolution.skill_store import SkillStore
from backend.memory.sqlite_backend import SQLiteBackend
from backend.memory.tree import MemoryTree
from backend.tools.registry import ToolRegistry
from backend.utils.logger import get_logger


def test_reflector_generates_pending_skill_from_trace(tmp_path: Path):
    sqlite = SQLiteBackend(tmp_path / "agent.db")
    memory = MemoryTree(sqlite)
    skills = SkillStore(tmp_path / "skills", sqlite=sqlite)
    tools = ToolRegistry(tmp_path, memory=memory, skill_store=skills)
    dispatcher = Dispatcher(tools, get_logger("test"), sqlite=sqlite)
    reflector = Reflector(tmp_path, memory, get_logger("test"), dispatcher=dispatcher, skill_store=skills)
    tools.bind(reflector=reflector)

    async def run_tool():
        return await dispatcher.dispatch("system_status", {})

    result = asyncio.run(run_tool())
    assert result["ok"] is True

    reflection = reflector.reflect("test trace")
    assert reflection["status"] == "recorded"
    assert reflection["draft_skill"] is not None
    assert skills.list()[0]["status"] == "pending"
