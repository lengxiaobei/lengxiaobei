"""Unified runtime settings loaded from environment and optional .env files."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


# -- field defaults (single source of truth) ----------------------------------
_DEFAULTS: dict[str, object] = {
    "project_root": PROJECT_ROOT,
    "data_dir": PROJECT_ROOT / "data",
    "backend_host": "127.0.0.1",
    "backend_port": 8000,
    "backend_cors_origins": ["http://127.0.0.1:5173", "http://localhost:5173"],
    "llm_provider": "ollama",
    "llm_model": "llama3.1",
    "llm_base_url": "http://127.0.0.1:11434",
    "llm_api_key": "",
    "llm_fallbacks": "",
    "mcp_servers_json": "",
    "skill_dirs": "",
    "max_sessions": 50,
    "session_context_tokens": 200000,
    "memory_auto_recall": True,
    "memory_max_results": 5,
    "memory_promotion_threshold": 0.8,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "whatsapp_bridge_url": "",
    "whatsapp_bridge_token": "",
    "slack_bot_token": "",
    "slack_channel_id": "",
    "local_agent_roots": [],
    "local_agents_config": PROJECT_ROOT / "data" / "local_agents.json",
    "chroma_path": PROJECT_ROOT / "data" / "chroma",
    "database_url": "sqlite:///data/sqlite/agent.db",
    "redis_url": "redis://127.0.0.1:6379/0",
    "llm_claude_enable_tools": False,
    "llm_claude_enable_caching": False,
    "llm_claude_thinking_budget": 0,
}

_ENV_MAP: dict[str, str] = {
    "data_dir": "DATA_DIR",
    "backend_host": "BACKEND_HOST",
    "backend_port": "BACKEND_PORT",
    "backend_cors_origins": "BACKEND_CORS_ORIGINS",
    "llm_provider": "LLM_PROVIDER",
    "llm_model": "LLM_MODEL",
    "llm_base_url": "LLM_BASE_URL",
    "llm_api_key": "LLM_API_KEY",
    "llm_fallbacks": "LLM_FALLBACKS",
    "mcp_servers_json": "MCP_SERVERS_JSON",
    "skill_dirs": "SKILL_DIRS",
    "max_sessions": "MAX_SESSIONS",
    "session_context_tokens": "SESSION_CONTEXT_TOKENS",
    "memory_auto_recall": "MEMORY_AUTO_RECALL",
    "memory_max_results": "MEMORY_MAX_RESULTS",
    "memory_promotion_threshold": "MEMORY_PROMOTION_THRESHOLD",
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    "telegram_chat_id": "TELEGRAM_CHAT_ID",
    "whatsapp_bridge_url": "WHATSAPP_BRIDGE_URL",
    "whatsapp_bridge_token": "WHATSAPP_BRIDGE_TOKEN",
    "slack_bot_token": "SLACK_BOT_TOKEN",
    "slack_channel_id": "SLACK_CHANNEL_ID",
    "local_agent_roots": "LOCAL_AGENT_ROOTS",
    "local_agents_config": "LOCAL_AGENTS_CONFIG",
    "chroma_path": "CHROMA_PATH",
    "database_url": "DATABASE_URL",
    "redis_url": "REDIS_URL",
    "llm_claude_enable_tools": "LLM_CLAUDE_ENABLE_TOOLS",
    "llm_claude_enable_caching": "LLM_CLAUDE_ENABLE_CACHING",
    "llm_claude_thinking_budget": "LLM_CLAUDE_THINKING_BUDGET",
}

_LIST_FIELDS = frozenset({"backend_cors_origins", "local_agent_roots"})
_PATH_FIELDS = frozenset({"project_root", "data_dir", "local_agents_config", "chroma_path"})
_INT_FIELDS = frozenset({"backend_port", "llm_claude_thinking_budget"})


# -- try pydantic-settings first -----------------------------------------------
try:
    from pydantic import field_validator
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        project_root: Path = _DEFAULTS["project_root"]  # type: ignore[assignment]
        data_dir: Path = _DEFAULTS["data_dir"]  # type: ignore[assignment]
        backend_host: str = "127.0.0.1"
        backend_port: int = 8000
        backend_cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
        llm_provider: str = "ollama"
        llm_model: str = "llama3.1"
        llm_base_url: str = "http://127.0.0.1:11434"
        llm_api_key: str = ""
        telegram_bot_token: str = ""
        telegram_chat_id: str = ""
        whatsapp_bridge_url: str = ""
        whatsapp_bridge_token: str = ""
        slack_bot_token: str = ""
        slack_channel_id: str = ""
        local_agent_roots: list[str] = []
        local_agents_config: Path = _DEFAULTS["local_agents_config"]  # type: ignore[assignment]
        chroma_path: Path = _DEFAULTS["chroma_path"]  # type: ignore[assignment]
        database_url: str = "sqlite:///data/sqlite/agent.db"
        redis_url: str = "redis://127.0.0.1:6379/0"
        llm_claude_enable_tools: bool = False
        llm_claude_enable_caching: bool = False
        llm_claude_thinking_budget: int = 0

        @field_validator("backend_cors_origins", mode="before")
        @classmethod
        def _parse_origins(cls, value):
            if isinstance(value, str):
                return _split_csv(value)
            return value

        @field_validator("local_agent_roots", mode="before")
        @classmethod
        def _parse_local_agent_roots(cls, value):
            if isinstance(value, str):
                return _split_csv(value)
            return value

        model_config = SettingsConfigDict(
            env_file=PROJECT_ROOT / ".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            extra="ignore",
        )

except Exception:

    class Settings:
        """Thin fallback that reads env vars / .env without pydantic-settings."""

        def __init__(self) -> None:
            env_file = _load_dotenv(PROJECT_ROOT / ".env")

            def _env(name: str, default: object) -> object:
                env_key = _ENV_MAP.get(name, name.upper())
                raw = os.getenv(env_key, env_file.get(env_key))
                if raw is None:
                    return default
                if name in _LIST_FIELDS:
                    return _split_csv(raw)
                if name in _INT_FIELDS:
                    return int(raw)
                if name in _PATH_FIELDS:
                    return Path(raw)
                return raw

            for field, default in _DEFAULTS.items():
                setattr(self, field, _env(field, default))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
