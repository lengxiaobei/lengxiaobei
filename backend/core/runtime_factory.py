"""Runtime factory shared by FastAPI and legacy Flask compatibility routes."""

from __future__ import annotations

import time
from pathlib import Path

from backend.agents.local import LocalAgentHub
from backend.config import get_settings
from backend.autonomy.agent_loop import AgentLoop, AgentConfig
from backend.autonomy.tools import register_all as register_agent_tools, register_dispatcher_tools, register_goals_tool
from backend.autonomy.loop import AutonomyEngine
from backend.core.commander import Commander
from backend.core.context import RuntimeContext
from backend.core.dispatcher import Dispatcher
from backend.evolution.burn import BurnEngine
from backend.evolution.reflector import Reflector
from backend.evolution.skill_store import SkillStore
from backend.evolution.brain_hooks import BrainHooks
from backend.memory.graph_store import GraphStore
from backend.memory.sqlite_backend import SQLiteBackend, SQLiteMemoryBackend
from backend.memory.sync.manager import SyncManager
from backend.memory.tree import MemoryTree
from backend.memory.user_profile import UserProfileManager
from backend.memory.vector_store import VectorStore
from backend.tools.registry import ToolRegistry
from backend.core.llm.router import get_router, ProviderRouter, ProviderConfig, ModelSpec
from backend.tools.mcp_client import get_mcp_manager, MCPManager, init_mcp
from backend.memory.hooks import get_memory_hooks, MemoryHooks
from backend.tools.skills_loader import get_skill_loader, SkillLoader
from backend.autonomy.context_compressor import ContextCompressor
from backend.autonomy.fact_extractor import FactExtractor
from backend.autonomy.review_engine import ReviewEngine
from backend.core.session import get_session_manager, SessionManager
from backend.utils.logger import get_logger
from backend.utils.task_queue import RuntimeScheduler


_logger = get_logger(__name__)


def build_runtime(project_root: Path | None = None, data_dir: Path | None = None, logger_name: str = "backend.gateway") -> RuntimeContext:
    """Build the shared agent runtime once per app process."""
    settings = get_settings()
    root = project_root or settings.project_root
    data = data_dir or settings.data_dir
    logger = get_logger(logger_name)

    sqlite = SQLiteBackend(data / "sqlite" / "agent.db")
    memory_tree = MemoryTree(sqlite)  # VectorStore wired up below
    vector_store = VectorStore(memory_tree, sqlite=sqlite, persist_dir=str(data / "chroma"))
    memory_tree.vector_store = vector_store  # Enable hybrid search
    graph_store = GraphStore(sqlite)
    sync_manager = SyncManager(memory_tree, sqlite=sqlite)
    skill_store = SkillStore(data / "skills", sqlite=sqlite)
    agent_roots = [Path(item).expanduser() for item in getattr(settings, "local_agent_roots", [])]
    agent_hub = LocalAgentHub(
        roots=agent_roots or None,
        config_path=Path(settings.local_agents_config).expanduser(),
    )
    tools = ToolRegistry(
        root,
        memory=memory_tree,
        skill_store=skill_store,
        vector_store=vector_store,
        agent_hub=agent_hub,
    )
    dispatcher = Dispatcher(tools=tools, logger=logger, sqlite=sqlite)
    reflector = Reflector(
        project_root=root,
        memory=memory_tree,
        logger=logger,
        dispatcher=dispatcher,
        skill_store=skill_store,
    )
    tools.bind(reflector=reflector, vector_store=vector_store)
    burn = BurnEngine(reflector=reflector, skill_store=skill_store, dispatcher=dispatcher, memory=memory_tree, logger=logger, data_dir=data)
    autonomy = AutonomyEngine(
        data_dir=data,
        memory=memory_tree,
        dispatcher=dispatcher,
        skill_store=skill_store,
        logger=logger,
        idle_check=lambda: time.time() - runtime.last_activity_at if runtime.last_activity_at else None,
    )

    # ── Agent Loop ────────────────────────────────────────────────────
    agent_memory = SQLiteMemoryBackend(data / "memory.db")
    agent_loop_config = AgentConfig(
        max_turns_per_session=50,
        recall_limit=12,
        tool_timeout_seconds=30.0,
        memory_promotion_interval_seconds=30 * 60,
        goal_check_interval_seconds=10 * 60,
        prune_threshold=5000,
    )
    agent_loop = AgentLoop(
        memory=agent_memory,
        config=agent_loop_config,
        tools={},  # Tools registered below
        llm_completer=None,  # Wired after LLM router is ready
        logger=logger,
        trace_backend=sqlite,
    )
    # Register all agent tools
    register_agent_tools(agent_loop)
    register_dispatcher_tools(agent_loop, dispatcher, tools)
    register_goals_tool(agent_loop, autonomy)

    # ── LLM Router ─────────────────────────────────────────────────────
    llm_router = get_router()

    # Wire LLM completer to agent loop (after router is ready)
    async def _llm_complete(prompt: str, system: str = "", history: list | None = None) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.extend(history or [{"role": "user", "content": prompt}])
        result = await llm_router.chat(messages)
        if result.get("error"):
            # Raise instead of returning error text — let _call_llm catch it
            raise RuntimeError(f"LLM router error: {result['error']}")
        content = str(result.get("content") or "")
        if not content:
            raise RuntimeError("LLM returned empty content")
        return content

    agent_loop.llm_completer = _llm_complete

    # ── BrainHooks: Hermes Brain ↔ OpenClaw Body real-time integration ──
    brain_hooks = BrainHooks(
        reflector=reflector,
        skill_store=skill_store,
        memory=memory_tree,
        dispatcher=dispatcher,
        llm_completer=_llm_complete,
        logger=logger,
        enable_recovery=True,
        enable_micro_reflection=True,
        enable_skill_injection=True,
    )
    agent_loop.brain_hooks = brain_hooks

    # ── Phase 5: Context Compression & Fact Extraction ────────────────
    context_compressor = ContextCompressor(
        llm_completer=_llm_complete,
        max_messages=20,
        keep_recent=6,
    )
    fact_extractor = FactExtractor(
        memory=memory_tree,
        llm_completer=_llm_complete,
        extract_interval=5,
    )
    agent_loop.context_compressor = context_compressor
    agent_loop.fact_extractor = fact_extractor

    # ── MCP & Hooks ────────────────────────────────────────────────────
    mcp_manager = get_mcp_manager()
    memory_hooks = get_memory_hooks(memory_tree=memory_tree, vector_store=vector_store)
    session_manager = get_session_manager()
    skill_loader = get_skill_loader(tool_registry=tools)

    # Wire MCP tools into ToolRegistry
    for tool_name, mcp_tool in mcp_manager.get_tools().items():
        tools.register(tool_name, lambda _t=mcp_tool, **kw: _t)

    scheduler = RuntimeScheduler(logger)
    scheduler.add_interval_job("memory-reindex", 20 * 60, lambda: vector_store.reindex(limit=1000))
    scheduler.add_interval_job("reflection", 30 * 60, lambda: reflector.reflect("scheduled reflection", force_skill=True))
    scheduler.add_interval_job("autonomy-loop", 15 * 60, lambda: autonomy.tick("scheduled autonomy loop"))
    scheduler.add_interval_job("memory-promotion", 30 * 60, lambda: _run_promotion(memory_hooks, settings))
    scheduler.add_interval_job("mcp-health", 10 * 60, lambda: _check_mcp(mcp_manager))
    scheduler.add_interval_job("code-quality-check", 60 * 60, lambda: autonomy.tick("scheduled code quality check", force=True))
    scheduler.add_interval_job("auto-skill-demotion", 60 * 60, lambda: skill_store.auto_demote(min_uses=5, min_success_rate=30.0))

    # ── Phase 5: Review Engine ──────────────────────────────────────────
    review_engine = ReviewEngine(
        sqlite=sqlite,
        memory=memory_tree,
        skill_store=skill_store,
        llm_completer=_llm_complete,
    )
    # Daily review at 2am, weekly cleanup at 3am
    scheduler.add_interval_job("daily-review", 24 * 60 * 60, lambda: review_engine.daily_review())
    scheduler.add_interval_job("weekly-cleanup", 7 * 24 * 60 * 60, lambda: review_engine.cleanup_stale(max_age_days=30))
    user_profile = UserProfileManager(sqlite)
    commander = Commander(dispatcher=dispatcher, memory=memory_tree, logger=logger, user_profile=user_profile, agent_loop=agent_loop)

    runtime = RuntimeContext(
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
        autonomy=autonomy,
        reflector=reflector,
        skill_store=skill_store,
        scheduler=scheduler,
        burn=burn,
        llm_router=llm_router,
        mcp_manager=mcp_manager,
        memory_hooks=memory_hooks,
        session_manager=session_manager,
        skill_loader=skill_loader,
        agent_loop=agent_loop,
        brain_hooks=brain_hooks,
        context_compressor=context_compressor,
        fact_extractor=fact_extractor,
        review_engine=review_engine,
        started_at=time.time(),
        logger=logger,
        last_activity_at=time.time(),
    )
    autonomy.emit = runtime.emit
    return runtime


async def _run_promotion(hooks: MemoryHooks, settings: Any) -> None:
    """Run memory promotion cycle."""
    try:
        memory_md = Path(settings.project_root) / "MEMORY.md"
        await hooks.run_promotion_cycle(str(memory_md))
    except Exception as exc:
        _logger.warning("Memory promotion cycle failed: %s", exc, exc_info=True)


async def _check_mcp(manager: MCPManager) -> None:
    """Reconnect any disconnected MCP servers."""
    try:
        for name in manager._servers:
            if not manager.is_connected(name):
                await manager.connect_server(name)
    except Exception as exc:
        _logger.warning("MCP health check failed: %s", exc, exc_info=True)