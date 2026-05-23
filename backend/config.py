"""Unified runtime settings loaded from environment and optional .env files."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


try:
    from pydantic import field_validator
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        project_root: Path = PROJECT_ROOT
        data_dir: Path = PROJECT_ROOT / "data"
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
        chroma_path: Path = PROJECT_ROOT / "data" / "chroma"
        database_url: str = "sqlite:///data/sqlite/agent.db"
        redis_url: str = "redis://127.0.0.1:6379/0"

        @field_validator("backend_cors_origins", mode="before")
        @classmethod
        def _parse_origins(cls, value):
            if isinstance(value, str):
                return _split_csv(value)
            return value

        model_config = SettingsConfigDict(
            env_file=PROJECT_ROOT / ".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
        )

except Exception:

    class Settings:
        """Small fallback when pydantic-settings is not installed yet."""

        def __init__(self) -> None:
            self.project_root = PROJECT_ROOT
            self.data_dir = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))
            self.backend_host = os.getenv("BACKEND_HOST", "127.0.0.1")
            self.backend_port = int(os.getenv("BACKEND_PORT", "8000"))
            self.backend_cors_origins = _split_csv(
                os.getenv("BACKEND_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
            )
            self.llm_provider = os.getenv("LLM_PROVIDER", "ollama")
            self.llm_model = os.getenv("LLM_MODEL", "llama3.1")
            self.llm_base_url = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434")
            self.llm_api_key = os.getenv("LLM_API_KEY", "")
            self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            self.whatsapp_bridge_url = os.getenv("WHATSAPP_BRIDGE_URL", "")
            self.whatsapp_bridge_token = os.getenv("WHATSAPP_BRIDGE_TOKEN", "")
            self.slack_bot_token = os.getenv("SLACK_BOT_TOKEN", "")
            self.slack_channel_id = os.getenv("SLACK_CHANNEL_ID", "")
            self.chroma_path = Path(os.getenv("CHROMA_PATH", str(PROJECT_ROOT / "data" / "chroma")))
            self.database_url = os.getenv("DATABASE_URL", "sqlite:///data/sqlite/agent.db")
            self.redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
