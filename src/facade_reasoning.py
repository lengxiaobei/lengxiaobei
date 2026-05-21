"""
推理系统 Facade — 懒加载查询引擎、工具、技能、模型路由等

含: query_engine, tool_registry, tool_builder, skill_manager, integration_manager
模型路由统一使用 llm.route()
"""

from pathlib import Path


class ReasoningFacade:

    def __init__(self, project_root: Path, memory_facade):
        self._project_root = project_root
        self._memory_facade = memory_facade
        self._query_engine = None
        self._tool_registry = None
        self._tool_builder = None
        self._skill_manager = None
        self._integration_manager = None
        self._model_router = None

    @property
    def tool_registry(self):
        if self._tool_registry is None:
            from .tool_registry import ToolRegistry

            self._tool_registry = ToolRegistry(str(self._project_root))
        return self._tool_registry

    @property
    def tool_builder(self):
        if self._tool_builder is None:
            from .tool_builder import ToolBuilder

            tools_dir = self._project_root / "tools"
            tools_dir.mkdir(exist_ok=True)
            self._tool_builder = ToolBuilder(
                str(tools_dir), registry=self.tool_registry
            )
        return self._tool_builder

    @property
    def skill_manager(self):
        if self._skill_manager is None:
            from .skills import create_skill_manager

            self._skill_manager = create_skill_manager(str(self._project_root))
        return self._skill_manager

    @property
    def query_engine(self):
        if self._query_engine is None:
            from .query_engine import QueryEngineConfig, QueryEngineV2

            qe_config = QueryEngineConfig(
                cwd=str(self._project_root),
                tools=self.tool_registry,
                memory=self._memory_facade.memory,
            )
            self._query_engine = QueryEngineV2(qe_config)
        return self._query_engine

    @property
    def integration_manager(self):
        if self._integration_manager is None:
            from .integration import create_integration_manager

            self._integration_manager = create_integration_manager(
                str(self._project_root)
            )
            if hasattr(self, "_skill_manager") and self._skill_manager is not None:
                self._skill_manager.integration_manager = self._integration_manager
                self._skill_manager._load_external_skills()
        return self._integration_manager

    @property
    def model_router(self):
        """模型路由 — 委托给 llm.route()，返回路由模块"""
        if self._model_router is None:
            from . import llm
            self._model_router = llm
        return self._model_router