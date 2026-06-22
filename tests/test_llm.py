"""LLM connectivity and routing tests.

Verifies the model factory wires up correctly for the configured provider,
with focused checks for the ollama/self-hosted path.

Run with:
    pytest tests/test_llm.py -v -s
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provider() -> str:
    return os.getenv("LLM_PROVIDER", "anthropic").lower()


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestConfig:
    def test_provider_is_set(self):
        from burry.config import get_settings
        s = get_settings()
        assert s.llm_provider in ("anthropic", "openai", "ollama", "gemini"), \
            f"Unknown provider: {s.llm_provider}"
        print(f"\n  Provider: {s.llm_provider}")

    def test_ollama_settings_when_active(self):
        from burry.config import get_settings
        s = get_settings()
        if s.llm_provider != "ollama":
            pytest.skip("Provider is not ollama")
        assert s.ollama_base_url, "OLLAMA_BASE_URL is not set"
        assert s.ollama_model,    "OLLAMA_MODEL is not set"
        print(f"\n  Base URL : {s.ollama_base_url}")
        print(f"  Default model: {s.ollama_model}")

    def test_gemini_settings_when_active(self):
        from burry.config import get_settings
        s = get_settings()
        if s.llm_provider != "gemini":
            pytest.skip("Provider is not gemini")
        assert s.gemini_api_key, "GEMINI_API_KEY is not set"
        assert s.gemini_model,   "GEMINI_MODEL is not set"
        print(f"\n  Default model : {s.gemini_model}")
        print(f"  Critic model  : {s.gemini_model_critic or '(default)'}")
        print(f"  Technical     : {s.gemini_model_technical or '(default)'}")
        print(f"  Macro         : {s.gemini_model_macro or '(default)'}")


# ---------------------------------------------------------------------------
# Model factory — role routing
# ---------------------------------------------------------------------------

class TestModelFactory:
    def test_get_llm_returns_chat_model(self):
        from langchain_core.language_models.chat_models import BaseChatModel
        from burry.models import get_llm
        llm = get_llm("default")
        assert isinstance(llm, BaseChatModel)

    def test_all_agent_roles_instantiate(self):
        """Every role used in the graph must resolve without error."""
        from burry.models import get_llm
        roles = ["default", "technical", "macro", "critic", "massive"]
        for role in roles:
            llm = get_llm(role)
            assert llm is not None, f"get_llm('{role}') returned None"
            model = getattr(llm, 'model', getattr(llm, 'model_name', '?'))
            print(f"\n  role={role!r:12}  model={model}")

    def test_ollama_role_override(self):
        from burry.config import get_settings
        from burry.models import _ollama_model_for_role
        s = get_settings()
        if s.llm_provider != "ollama":
            pytest.skip("Provider is not ollama")
        default = _ollama_model_for_role("default")
        critic  = _ollama_model_for_role("critic")
        if s.ollama_model_critic:
            assert critic == s.ollama_model_critic
        else:
            assert critic == default
        print(f"\n  critic model: {critic}")

    def test_gemini_role_override(self):
        from burry.config import get_settings
        from burry.models import _gemini_model_for_role
        s = get_settings()
        if s.llm_provider != "gemini":
            pytest.skip("Provider is not gemini")
        for role in ["technical", "macro", "critic"]:
            model = _gemini_model_for_role(role)
            assert model, f"No model resolved for role '{role}'"
            print(f"\n  role={role!r:12}  model={model}")


# ---------------------------------------------------------------------------
# Live connectivity — Gemini
# ---------------------------------------------------------------------------

class TestGeminiConnectivity:
    @pytest.fixture(autouse=True)
    def require_gemini(self):
        if _provider() != "gemini":
            pytest.skip("Provider is not gemini")

    def test_simple_inference(self):
        from burry.models import get_llm
        from langchain_core.messages import HumanMessage
        llm = get_llm("default", temperature=0)
        resp = llm.invoke([HumanMessage(content="Reply with the single word: pong")])
        content = resp.content.strip()
        assert content, "Got empty response from Gemini"
        print(f"\n  Gemini response: {content!r}")

    def test_all_agent_roles_respond(self):
        from burry.models import get_llm
        from langchain_core.messages import HumanMessage
        for role in ["technical", "macro", "critic"]:
            llm = get_llm(role, temperature=0)
            resp = llm.invoke([HumanMessage(content=f"Role={role}. Reply: ok")])
            assert resp.content.strip(), f"Empty response for role '{role}'"
            model = getattr(llm, 'model', '?')
            print(f"\n  role={role!r:12} model={model}  → {resp.content.strip()[:60]!r}")


# ---------------------------------------------------------------------------
# Live connectivity — Ollama
# ---------------------------------------------------------------------------

class TestOllamaConnectivity:
    @pytest.fixture(autouse=True)
    def require_ollama(self):
        if _provider() != "ollama":
            pytest.skip("Provider is not ollama — skipping connectivity checks")

    def test_ollama_endpoint_reachable(self):
        """Check the base URL responds before we try an LLM call.

        Open WebUI root is at the host root, not at /ollama — we strip the
        /ollama suffix to ping the UI itself.
        """
        import urllib.request
        base = _base_url().rstrip("/")
        # Ping the root of the host (works for both raw Ollama and Open WebUI)
        root = base.replace("/ollama", "")
        try:
            req = urllib.request.Request(root, headers={"User-Agent": "burry-test"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                print(f"\n  {root} → HTTP {resp.status} ✓")
        except Exception as exc:
            pytest.fail(
                f"Cannot reach {root}: {exc}\n"
                f"  Make sure you are on the same network as the Open WebUI instance\n"
                f"  and OLLAMA_BASE_URL is set correctly in .env"
            )

    def test_openai_compat_models_endpoint(self):
        """The /v1/models endpoint must list at least one model."""
        import json, urllib.request
        from burry.config import get_settings
        s = get_settings()
        url = f"{s.ollama_base_url.rstrip('/')}/v1/models"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {s.ollama_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = json.loads(resp.read())
            models = [m["id"] for m in body.get("data", [])]
            assert models, f"No models listed at {url}"
            print(f"\n  Available models ({len(models)}): {models[:10]}")
            if len(models) > 10:
                print(f"  ... and {len(models) - 10} more")
        except Exception as exc:
            pytest.fail(
                f"Could not list models from {url}: {exc}\n"
                f"  If using Open WebUI, make sure OLLAMA_API_KEY is set to your\n"
                f"  account token (Profile → Settings → Account → API Keys)"
            )

    def test_configured_model_is_available(self):
        """The model in OLLAMA_MODEL must be listed by the API."""
        import json, urllib.request
        from burry.config import get_settings
        s = get_settings()
        url = f"{s.ollama_base_url.rstrip('/')}/v1/models"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {s.ollama_api_key}"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read())
        available = [m["id"] for m in body.get("data", [])]
        assert s.ollama_model in available, (
            f"Model '{s.ollama_model}' not found.\n"
            f"  Available: {available}\n"
            f"  Pull it in Open WebUI or run: ollama pull {s.ollama_model}"
        )
        print(f"\n  Model '{s.ollama_model}' is available ✓")

    def test_simple_inference(self):
        """Send a trivial prompt and verify we get a non-empty string back."""
        from burry.models import get_llm
        from langchain_core.messages import HumanMessage
        llm = get_llm("default", temperature=0)
        response = llm.invoke([HumanMessage(content="Reply with the single word: pong")])
        content = response.content.strip()
        assert content, "Got empty response from model"
        print(f"\n  Model response: {content!r}")

    def test_all_agent_roles_respond(self):
        """Each agent role must complete a short inference successfully."""
        from burry.models import get_llm
        from langchain_core.messages import HumanMessage
        roles = ["technical", "macro", "critic"]
        for role in roles:
            llm = get_llm(role, temperature=0)
            resp = llm.invoke([HumanMessage(content=f"Role={role}. Reply: ok")])
            assert resp.content.strip(), f"Empty response for role '{role}'"
            print(f"\n  role={role!r:12}  → {resp.content.strip()!r}")
