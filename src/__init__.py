"""
冷小北 · Leng Xiaobei
===================
数字生命体 — 自演化 AI Agent

使用延迟导入减少包级副作用。
直接导入子模块以获得更好的 IDE 支持：
    from src.core import LengXiaobei
    from src.constitution import Constitution
"""

__version__ = "Phase 2.1"
__author__ = "冷小北"

import importlib


_MODULE_MAP = {
    # 核心 (核心路径)
    "Config": "config",
    "Memory": "memory",
    "chat": "llm",
    "route": "llm",
    "has_any_key": "llm",
    "reload_keys": "llm",
    "model_status": "llm",
    "Constitution": "constitution",
    "get_constitution": "constitution",

    # 查询引擎
    "QueryEngineV2": "query_engine",
    "QueryEngineConfig": "query_engine",
    "Message": "query_engine",
    "ToolUse": "query_engine",
    "ToolResult": "query_engine",
    "Usage": "query_engine",
    "PermissionDenial": "query_engine",
    "ask": "query_engine",
    "create_query_engine": "query_engine",

    # Evolution
    "EvolutionEngine": "evolution.engine",
    "AuditTrail": "evolution.audit",
    "AuditEntry": "evolution.audit",
    "AutonomousEvolutionEngine": "evolution.engine",
    "create_autonomous_evolution_engine": "evolution.engine",

    # 记忆 & 梦境
    "AutoDreamV2": "auto_dream",
    "DreamConfig": "auto_dream",
    "DreamProgress": "auto_dream",
    "DreamResult": "auto_dream",
    "execute_auto_dream": "auto_dream",
    "KnowledgeCurator": "knowledge_curator",
    "Pattern": "knowledge_curator",
    "PatternState": "knowledge_curator",
    "create_knowledge_curator": "knowledge_curator",

    # KAIROS 守护
    "Kairos": "kairos",
    "KairosState": "kairos",
    "KairosConfig": "kairos",
    "DailyLogManager": "kairos",
    "CronScheduler": "kairos",
    "create_kairos": "kairos",
    "EventBus": "kairos.events",
    "EventBusNotInitialized": "kairos.events",
    "init_event_bus": "kairos.events",
    "emit": "kairos.events",
    "subscribe": "kairos.events",

    # 工具系统
    "ToolRegistry": "tool_registry",
    "ToolSpec": "tool_registry",
    "Tool": "tool_registry",
    "ToolBuilder": "tool_builder",
    "Learner": "learner",
    "SelfAssessmentSystem": "self_assessment",
    "Ability": "self_assessment",
    "ErrorRecord": "self_assessment",
    "create_self_assessment_system": "self_assessment",

    # Hook / Skill
    "HookManager": "hooks",
    "HookEvent": "hooks",
    "BaseHook": "hooks",
    "BashCommandHook": "hooks",
    "PromptHook": "hooks",
    "HttpHook": "hooks",
    "AgentHook": "hooks",
    "HookMatcher": "hooks",
    "create_hook_manager": "hooks",
    "Skill": "skills",
    "SkillManager": "skills",
    "create_skill_manager": "skills",

    # MCP
    "ConfigScope": "mcp",
    "Transport": "mcp",
    "McpStdioServerConfig": "mcp",
    "McpSSEServerConfig": "mcp",
    "McpHTTPServerConfig": "mcp",
    "McpWebSocketServerConfig": "mcp",
    "McpSdkServerConfig": "mcp",
    "ScopedMcpServerConfig": "mcp",
    "ServerConnectionType": "mcp",
    "ConnectedMCPServer": "mcp",
    "FailedMCPServer": "mcp",
    "NeedsAuthMCPServer": "mcp",
    "PendingMCPServer": "mcp",
    "DisabledMCPServer": "mcp",
    "MCPClient": "mcp",
    "MCPConnectionManager": "mcp",
    "create_mcp_manager": "mcp",

    # Buddy
    "Rarity": "buddy",
    "Species": "buddy",
    "Eye": "buddy",
    "Hat": "buddy",
    "StatName": "buddy",
    "CompanionBones": "buddy",
    "Companion": "buddy",
    "BuddyManager": "buddy",
    "create_buddy_manager": "buddy",

    # Bridge
    "SpawnMode": "bridge",
    "SessionStatus": "bridge",
    "BridgeConfig": "bridge",
    "SessionHandle": "bridge",
    "SessionSpawnOpts": "bridge",
    "SessionSpawner": "bridge",
    "BridgeApiClient": "bridge",
    "BridgeLogger": "bridge",
    "run_bridge_loop": "bridge",
    "create_bridge_api_client": "bridge",
    "create_session_spawner": "bridge",
    "create_bridge_logger": "bridge",
    "create_bridge_config": "bridge",

    # State / Vim / Voice / Plugin / LSP / Notification / Team
    "Store": "state",
    "create_store": "state",
    "create_selector": "state",
    "AppState": "state",
    "select_session_status": "state",
    "select_ui_theme": "state",
    "select_memory_count": "state",
    "select_pending_changes": "state",
    "select_buddy_mood": "state",
    "select_app_summary": "state",
    "StateManager": "state",
    "create_state_manager": "state",
    "VoiceService": "voice",
    "create_voice_service": "voice",
    "VimModeManager": "vim",
    "create_vim_manager": "vim",
    "toggle_editor_mode": "vim",
    "PluginAuthor": "plugin",
    "PluginManifest": "plugin",
    "CommandMetadata": "plugin",
    "BuiltinPluginDefinition": "plugin",
    "PluginRepository": "plugin",
    "PluginConfig": "plugin",
    "LoadedPlugin": "plugin",
    "PluginComponent": "plugin",
    "PluginError": "plugin",
    "PluginLoadResult": "plugin",
    "PluginManager": "plugin",
    "create_plugin_manager": "plugin",
    "get_plugin_error_message": "plugin",
    "LspServerConfig": "lsp",
    "ScopedLspServerConfig": "lsp",
    "LspManager": "lsp",
    "create_lsp_manager": "lsp",
    "NotificationType": "notification",
    "NotificationPriority": "notification",
    "Notification": "notification",
    "NotificationManager": "notification",
    "create_notification_manager": "notification",
    "send_notification": "notification",
    "TeamRole": "team",
    "TeamMember": "team",
    "CollaborationSession": "team",
    "TaskStatus": "team",
    "Task": "team",
    "ActivityType": "team",
    "ActivityLog": "team",
    "TeamManager": "team",
    "create_team_manager": "team",

    # ForkedAgent
    "ForkedAgent": "forked_agent",
    "run_forked_agent": "forked_agent",
    "create_cache_safe_params": "forked_agent",
    "CacheSafeParams": "forked_agent",
    "ForkedAgentParams": "forked_agent",
    "ForkedAgentResult": "forked_agent",
    "SubagentContext": "forked_agent",

    # Permission / Budget
    "PermissionManager": "permission",
    "PermissionContext": "permission",
    "PermissionResult": "permission",
    "PermissionAudit": "permission",
    "create_wrapped_can_use_tool": "permission",
    "create_default_can_use_tool": "permission",
    "create_permission_manager": "permission",
    "check_permission": "permission",
    "get_permission_summary": "permission",
    "BudgetConfig": "budget",
    "BudgetStatus": "budget",
    "BudgetTracker": "budget",
    "TaskBudget": "budget",
    "create_budget_tracker": "budget",
    "create_task_budget": "budget",
    "calculate_cost": "budget",
    "format_budget_summary": "budget",
    "with_budget": "budget",

    # Error Handling (精简后已移除 error_handling 模块)

    # Model Router 已移除，统一使用 llm.route() / llm.classify_task()

    # JSON Schema / SDK Status / Debug / Performance
    "SchemaValidationResult": "json_schema",
    "SchemaConfig": "json_schema",
    "JsonSchemaValidator": "json_schema",
    "create_json_schema_validator": "json_schema",
    "validate_json": "json_schema",
    "validate_json_string": "json_schema",
    "generate_schema": "json_schema",
    "fix_validation_errors": "json_schema",
    "get_preset_schema": "json_schema",
    "PRESET_SCHEMAS": "json_schema",
    "SDKState": "sdk_status",
    "StateUpdate": "sdk_status",
    "SyncConfig": "sdk_status",
    "StatePersistenceConfig": "sdk_status",
    "SDKStatusManager": "sdk_status",
    "get_sdk_status_manager": "sdk_status",
    "start_sdk_status_manager": "sdk_status",
    "stop_sdk_status_manager": "sdk_status",
    "get_sdk_state": "sdk_status",
    "update_sdk_state": "sdk_status",
    "update_sdk_custom_state": "sdk_status",
    "register_sdk_state_listener": "sdk_status",
    "unregister_sdk_state_listener": "sdk_status",
    "sync_sdk_with_external": "sdk_status",
    "set_sdk_sync_config": "sdk_status",
    "set_sdk_persistence_config": "sdk_status",
    "DebugInfo": "debug",
    "TraceRecord": "debug",
    "DebugConfig": "debug",
    "DebugManager": "debug",
    "get_debug_manager": "debug",
    "set_debug_config": "debug",
    "debug_log": "debug",
    "debug_trace": "debug",
    "debug_profile": "debug",
    "get_trace_records": "debug",
    "get_debug_logs": "debug",
    "clear_trace_records": "debug",
    "clear_debug_logs": "debug",
    "dump_trace": "debug",
    "dump_logs": "debug",
    "debug_inspect": "debug",
    "debug_timeit": "debug",
    "debug_traceback": "debug",
    "debug_memory_usage": "debug",
    "CacheItem": "performance",
    "AsyncTask": "performance",
    "PerformanceConfig": "performance",
    "CacheManager": "performance",
    "AsyncManager": "performance",
    "PerformanceMetric": "performance",
    "PerformanceMonitor": "performance",
    "get_cache_manager": "performance",
    "get_async_manager": "performance",
    "cached": "performance",
    "async_cached": "performance",
    "async_wrap": "performance",
    "parallelize": "performance",
    "get_performance_monitor": "performance",
    "measure_performance": "performance",
    "async_measure_performance": "performance",
    "set_performance_config": "performance",
    "clear_cache": "performance",
    "get_cache_size": "performance",
    "run_async": "performance",
    "run_async_with_timeout": "performance",
    "run_async_all": "performance",

    # Config Manager (Enhanced)
    "ConfigSource": "config_enhanced",
    "ConfigValidationResult": "config_enhanced",
    "ConfigManager": "config_enhanced",

    # MCP Server / Logging / Monitoring
    "MCPServer": "mcp_server",
    "get_logger": "logging_config",
    "log_info": "logging_config",
    "log_warning": "logging_config",
    "log_error": "logging_config",
    "log_debug": "logging_config",
    "start_monitoring": "monitoring",
    "stop_monitoring": "monitoring",
    "get_system_metrics": "monitoring",
    "get_system_alerts": "monitoring",
    "clear_system_alerts": "monitoring",
}


def __getattr__(name):
    if name in _MODULE_MAP:
        module_name = _MODULE_MAP[name]
        try:
            module = importlib.import_module(f".{module_name}", __package__)
            attr = getattr(module, name)
            globals()[name] = attr
            return attr
        except (ImportError, AttributeError):
            return None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = sorted(_MODULE_MAP.keys())