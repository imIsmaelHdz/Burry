"""LLM factory — provider-agnostic.

Swap the whole stack between Anthropic and OpenAI with the LLM_PROVIDER env var.
Pass a `role` so different agents can later be pinned to different models/temps
(e.g. a cheap model for ingestion summaries, a strong one for the critic).
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from .config import get_settings


def get_llm(role: str = "default", *, temperature: float = 0.2) -> BaseChatModel:
    settings = get_settings()

    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=temperature,
            max_tokens=8_000,
        )

    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=temperature,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
