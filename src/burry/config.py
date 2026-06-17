"""Central configuration, loaded from environment / .env.

Everything tunable lives here so nodes and tools stay free of os.getenv calls.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM Provider
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    # Alpaca
    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_paper: bool = True

    # Market Data
    finnhub_api_key: str | None = None

    # Risk Limits
    max_position_pct: float = 0.10
    max_notional_per_order: float = 10_000.0
    max_open_positions: int = 15


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so we parse the environment exactly once."""
    return Settings()
