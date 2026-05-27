import asyncio
from pathlib import Path

from backend.autonomy.loop import AutonomyEngine
from backend.core.dispatcher import Dispatcher
from backend.evolution.skill_store import SkillStore
from backend.memory.sqlite_backend import SQLiteBackend
from backend.memory.tree import MemoryTree
from backend.tools.registry import ToolRegistry
from backend.utils.logger import get_logger


class FakeLearner:
    def learn(self, reference: str, limit: int = 2):
        return [
            {
                "reference": reference,
                "url": "https://example.test/reference",
                "title": "reference note",
                "summary": "useful autonomous learning",
                "ok": True,
            }
        ]


class FakeExecutor:
    def __init__(self, root: Path):
        self.root = root

    async def run_checks(self, include_expensive: bool = False):
        return {"ok": True, "checks": [], "expensive": include_expensive}

    async def write_roadmap(self, content: str):
        path = self.root / "data" / "autonomy" / "roadmap.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return {"ok": True, "result": {"path": str(path)}}

    async def append_changelog(self, content: str):
        return {"ok": True, "result": {"bytes": len(content)}}


async def _run_tick(tmp_path: Path):
    sqlite = SQLiteBackend(tmp_path / "agent.db")
    memory = MemoryTree(sqlite)
    skills = SkillStore(tmp_path / "skills", sqlite=sqlite)
    tools = ToolRegistry(tmp_path, memory=memory, skill_store=skills)
    dispatcher = Dispatcher(tools, get_logger("test-autonomy"), sqlite=sqlite)
    engine = AutonomyEngine(
        data_dir=tmp_path / "data",
        memory=memory,
        dispatcher=dispatcher,
        skill_store=skills,
        logger=get_logger("test-autonomy"),
    )
    engine.learner = FakeLearner()
    engine.executor = FakeExecutor(tmp_path)
    result = await engine.tick("test")
    return result, engine, memory, skills


def test_autonomy_tick_learns_executes_and_generates_skill(tmp_path: Path):
    result, engine, memory, skills = asyncio.run(_run_tick(tmp_path))

    assert result["status"] == "completed"
    assert result["checks"]["ok"] is True
    assert result["draft_skill"]["status"] == "pending"
    assert skills.list(status="pending")
    assert memory.search("autonomous learning", limit=1)
    assert (tmp_path / "data" / "autonomy" / "roadmap.md").exists()
    assert engine.status()["run_count"] == 1
    assert engine.status()["guards"]["daily_budget_used"] == 1


def test_autonomy_scheduled_tick_respects_idle_gate(tmp_path: Path):
    sqlite = SQLiteBackend(tmp_path / "agent.db")
    memory = MemoryTree(sqlite)
    skills = SkillStore(tmp_path / "skills", sqlite=sqlite)
    tools = ToolRegistry(tmp_path, memory=memory, skill_store=skills)
    dispatcher = Dispatcher(tools, get_logger("test-autonomy"), sqlite=sqlite)
    engine = AutonomyEngine(
        data_dir=tmp_path / "data",
        memory=memory,
        dispatcher=dispatcher,
        skill_store=skills,
        logger=get_logger("test-autonomy"),
        idle_check=lambda: 5,
        idle_seconds=60,
    )

    result = asyncio.run(engine.tick("scheduled autonomy loop"))

    assert result["status"] == "skipped"
    assert result["guard"]["reason"] == "not_idle"
    assert engine.status()["run_count"] == 0


def test_autonomy_scheduled_tick_respects_cooldown_and_budget(tmp_path: Path):
    sqlite = SQLiteBackend(tmp_path / "agent.db")
    memory = MemoryTree(sqlite)
    skills = SkillStore(tmp_path / "skills", sqlite=sqlite)
    tools = ToolRegistry(tmp_path, memory=memory, skill_store=skills)
    dispatcher = Dispatcher(tools, get_logger("test-autonomy"), sqlite=sqlite)
    engine = AutonomyEngine(
        data_dir=tmp_path / "data",
        memory=memory,
        dispatcher=dispatcher,
        skill_store=skills,
        logger=get_logger("test-autonomy"),
        idle_check=lambda: 999,
        cooldown_seconds=3600,
        daily_budget=1,
    )
    engine.state["last_run_at"] = __import__("time").time() - 10  # 10 seconds ago, well within cooldown

    cooldown = asyncio.run(engine.tick("scheduled autonomy loop"))
    assert cooldown["status"] == "skipped"
    assert cooldown["guard"]["reason"] == "cooldown"

    engine.state["last_run_at"] = 0
    engine.state["daily_budget"] = {"date": __import__("time").strftime("%Y-%m-%d"), "used": 1}
    budget = asyncio.run(engine.tick("scheduled autonomy loop"))
    assert budget["status"] == "skipped"
    assert budget["guard"]["reason"] == "daily_budget_exhausted"
