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
    assert reflection["skipped_reason"] is None
    assert skills.list()[0]["status"] == "pending"


def test_reflector_skips_when_no_successful_trace(tmp_path: Path):
    sqlite = SQLiteBackend(tmp_path / "agent.db")
    memory = MemoryTree(sqlite)
    skills = SkillStore(tmp_path / "skills", sqlite=sqlite)
    tools = ToolRegistry(tmp_path, memory=memory, skill_store=skills)
    dispatcher = Dispatcher(tools, get_logger("test"), sqlite=sqlite)
    reflector = Reflector(tmp_path, memory, get_logger("test"), dispatcher=dispatcher, skill_store=skills)

    reflection = reflector.reflect("empty trace")

    assert reflection["draft_skill"] is None
    assert reflection["skipped_reason"] == "no_new_successful_trace"
    assert skills.list() == []


def test_reflector_dedupes_same_trigger_within_window(tmp_path: Path):
    sqlite = SQLiteBackend(tmp_path / "agent.db")
    memory = MemoryTree(sqlite)
    skills = SkillStore(tmp_path / "skills", sqlite=sqlite)
    tools = ToolRegistry(tmp_path, memory=memory, skill_store=skills)
    dispatcher = Dispatcher(tools, get_logger("test"), sqlite=sqlite)
    reflector = Reflector(tmp_path, memory, get_logger("test"), dispatcher=dispatcher, skill_store=skills)
    tools.bind(reflector=reflector)

    async def run_tool():
        return await dispatcher.dispatch("system_status", {})

    asyncio.run(run_tool())
    first = reflector.reflect("repeat trigger")
    asyncio.run(run_tool())
    second = reflector.reflect("repeat trigger")

    assert first["draft_skill"] is not None
    assert second["draft_skill"] is None
    assert second["skipped_reason"] == "duplicate_trigger_within_7_days"
    assert len(skills.list()) == 1


def test_skill_review_persists_verification_metadata(tmp_path: Path):
    sqlite = SQLiteBackend(tmp_path / "agent.db")
    skills = SkillStore(tmp_path / "skills", sqlite=sqlite)
    skills.save(
        {
            "name": "verify_me",
            "trigger": "manual",
            "steps": [{"tool": "system_status", "args": {}}],
            "status": "pending",
        }
    )

    reviewed = skills.review(
        "verify_me",
        "approved",
        reviewer="evaluator",
        notes="Replay and tests passed.",
        evidence=["dispatcher replay succeeded", "pytest backend/tests/test_skill_gen.py -q"],
        checks={"replay_ok": True, "tests_ok": True},
        rollback_plan="Revert to pending if replay diverges.",
    )

    assert reviewed is not None
    assert reviewed["status"] == "approved"
    assert reviewed["latest_review"]["reviewer"] == "evaluator"
    assert reviewed["latest_review"]["checks"]["tests_ok"] is True
    assert reviewed["latest_review"]["rollback_plan"] == "Revert to pending if replay diverges."
    assert len(reviewed["review_history"]) == 1

    listed = skills.list(status="approved")
    assert listed
    assert listed[0]["body"]["latest_review"]["evidence"][0] == "dispatcher replay succeeded"
