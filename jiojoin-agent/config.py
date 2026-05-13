"""
config.py – Centralised settings for JioJoin Agent.
All values are read from environment variables (or a .env file).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Groq / LLM ──────────────────────────────────────────────────────────
    groq_api_key: str = "your_groq_api_key_here"
    groq_model: str = "llama-3.3-70b-versatile"
    agent_temperature: float = 0.6

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./jiojoin.db"

    # ── JWT Auth ─────────────────────────────────────────────────────────────
    jwt_secret_key: str = "change_me_in_production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 10080  # 7 days

    # ── Server ───────────────────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "development"

    # ── Agent behaviour ──────────────────────────────────────────────────────
    max_conversation_history: int = 20  # messages kept in context per session

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton – import and call this everywhere."""
    return Settings()
