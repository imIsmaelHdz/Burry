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

    # LLM Provider — "anthropic" | "openai" | "ollama" | "gemini"
    llm_provider: Literal["anthropic", "openai", "ollama", "gemini"] = "anthropic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    # Gemini (Google AI Studio)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"          # default for all agents
    gemini_model_technical: str = ""                 # override per role
    gemini_model_macro: str = ""
    gemini_model_critic: str = "gemini-2.5-flash"   # bump critic to flash too
    # Open WebUI API path: <OLLAMA_BASE_URL>/v1  (set base to .../ollama)
    # API key: Open WebUI account token (Profile → Settings → Account → API Keys)
    ollama_base_url: str = "http://localhost:11434"
    ollama_api_key: str = "ollama"        # raw Ollama needs any non-empty string; Open WebUI needs your account token
    ollama_model: str = "qwen2.5:3b"
    # Per-role model overrides — leave empty to fall back to ollama_model.
    # Format:  OLLAMA_MODEL_<ROLE>=<model_name>
    # Example: OLLAMA_MODEL_CRITIC=qwen2.5:7b
    ollama_model_technical: str = ""
    ollama_model_macro: str = ""
    ollama_model_critic: str = ""

    # Alpaca
    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_paper: bool = True

    # Market Data
    finnhub_api_key: str | None = None

    # Massive (optional extra research step — off unless explicitly enabled)
    massive_api_key: str | None = None
    enable_massive: bool = False

    # Crypto (Binance Futures F1-F5 protocol — off unless explicitly enabled)
    enable_crypto: bool = False
    crypto_capital: float = 1000.0   # default session capital in USD

    # Risk Limits
    max_position_pct: float = 0.10
    max_notional_per_order: float = 10_000.0
    max_open_positions: int = 15


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so we parse the environment exactly once."""
    return Settings()
