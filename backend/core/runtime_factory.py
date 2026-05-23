"""Runtime factory shared by FastAPI and legacy Flask compatibility routes."""

from __future__ import annotations

import time
from pathlib import Path

from backend.config import get_settings
from backend.core.commander import Commander
from backend.core.context import RuntimeContext
from backend.core.dispatcher import Dispatcher
from backend.evolution.reflector import Reflector
from backend.evolution.skill_store import SkillStore
from backend.memory.graph_store import GraphStore
from backend.memory.sqlite_backend import SQLiteBackend
from backend.memory.sync.manager import SyncManager
from backend.memory.tree import MemoryTree
from backend.memory.vector_store import VectorStore
from backend.tools.registry import ToolRegistry
from backend.utils.logger import get_logger
from backend.utils.task_queue import RuntimeScheduler


def build_runtime(project_root: Path | None = None, data_dir: Path | None = None, logger_name: str = "backend.gateway") -> RuntimeContext:
    """Build the shared agent runtime once per app process."""
    settings = get_settings()
    root = project_root or settings.project_root
    data = data_dir or settings.data_dir
    logger = get_logger(logger_name)

    sqlite = SQLiteBackend(data / "sqlite" / "agent.db")
    memory_tree = MemoryTree(sqlite)
    vector_store = VectorStore(memory_tree, sqlite=sqlite, persist_dir=str(data / "chroma"))
    graph_store = GraphStore(sqlite)
    sync_manager = SyncManager(memory_tree, sqlite=sqlite)
    skill_store = SkillStore(data / "skills", sqlite=sqlite)
    tools = ToolRegistry(root, memory=memory_tree, skill_store=skill_store, vector_store=vector_store)
    dispatcher = Dispatcher(tools=tools, logger=logger, sqlite=sqlite)
    reflector = Reflector(
        project_root=root,
        memory=memory_tree,
        logger=logger,
        dispatcher=dispatcher,
        skill_store=skill_store,
    )
    tools.bind(reflector=reflector, vector_store=vector_store)

    scheduler = RuntimeScheduler(logger)
    scheduler.add_interval_job("memory-reindex", 20 * 60, lambda: vector_store.reindex(limit=1000))
    scheduler.add_interval_job("hermes-reflect", 30 * 60, lambda: reflector.reflect("scheduled reflection", force_skill=True))
    commander = Commander(dispatcher=dispatcher, memory=memory_tree, logger=logger)

    return RuntimeContext(
        project_root=root,
        data_dir=data,
        sqlite=sqlite,
        memory=memory_tree,
        vector_store=vector_store,
        graph_store=graph_store,
        sync_manager=sync_manager,
        tools=tools,
        dispatcher=dispatcher,
        commander=commander,
        reflector=reflector,
        skill_store=skill_store,
        scheduler=scheduler,
        started_at=time.time(),
        logger=logger,
    )
