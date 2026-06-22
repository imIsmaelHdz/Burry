"""LLM factory — provider-agnostic.

Swap the whole stack between Anthropic, OpenAI, or a self-hosted
OpenAI-compatible endpoint (Ollama/Dokku) with the LLM_PROVIDER env var.

Role-based routing
------------------
Each agent passes its `role` so different agents can be pinned to different
models. With the ollama provider you can override per role:

    OLLAMA_MODEL_TECHNICAL=qwen2.5:7b   # heavier model for technical research
    OLLAMA_MODEL_MACRO=qwen2.5:7b
    OLLAMA_MODEL_CRITIC=qwen2.5:14b     # strongest model for the critic
    OLLAMA_MODEL=qwen2.5:3b             # default for everything else

Roles used by the agents: "technical", "macro", "critic", "massive", "default"
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from .config import get_settings


def _ollama_model_for_role(role: str) -> str:
    """Return the Ollama model name for a given agent role, with fallback."""
    s = get_settings()
    overrides = {
        "technical": s.ollama_model_technical,
        "macro":     s.ollama_model_macro,
        "critic":    s.ollama_model_critic,
    }
    return overrides.get(role) or s.ollama_model


def _gemini_model_for_role(role: str) -> str:
    """Return the Gemini model name for a given agent role, with fallback."""
    s = get_settings()
    overrides = {
        "technical": s.gemini_model_technical,
        "macro":     s.gemini_model_macro,
        "critic":    s.gemini_model_critic,
    }
    return overrides.get(role) or s.gemini_model


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

    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        model = _gemini_model_for_role(role)
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.gemini_api_key,
            temperature=temperature,
        )

    if settings.llm_provider == "ollama":
        from langchain_openai import ChatOpenAI

        model = _ollama_model_for_role(role)
        # Fall back to "ollama" if key is blank (raw Ollama needs any non-empty string)
        api_key = settings.ollama_api_key or "ollama"
        return ChatOpenAI(
            model=model,
            # Open WebUI:  base_url = http://<host>/ollama/v1
            # Raw Ollama:  base_url = http://<host>:11434/v1
            base_url=f"{settings.ollama_base_url.rstrip('/')}/v1",
            api_key=api_key,
            temperature=temperature,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
