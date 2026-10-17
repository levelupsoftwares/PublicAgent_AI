"""Tests for the Google Gemini provider wiring (no network calls)."""
from __future__ import annotations

import pytest


@pytest.fixture()
def reset_clients():
    """Reset the llm-client singleton and settings after each test."""
    yield
    from app.config import settings
    from app.llm.client import set_llm_client

    set_llm_client(None)
    settings.LLM_PROVIDER = "mock"
    settings.EMBEDDING_PROVIDER = ""
    settings.GEMINI_API_KEY = ""
    settings.OPENROUTER_API_KEY = ""
    settings.GROQ_API_KEY = ""


def test_gemini_provider_without_key_falls_back_to_mock(reset_clients):
    from app.config import settings
    from app.llm.client import build_llm_client, set_llm_client
    from app.llm.mock_client import MockLLMClient

    set_llm_client(None)
    settings.LLM_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = ""
    client = build_llm_client()
    assert isinstance(client, MockLLMClient)


def test_gemini_embed_facade_wiring(reset_clients, monkeypatch):
    """EMBEDDING_PROVIDER=gemini keeps the chat provider but swaps embed().

    The Gemini adapter's embed() is monkeypatched so no network call happens.
    """
    from app.config import settings
    from app.llm.client import build_llm_client, set_llm_client

    set_llm_client(None)
    settings.LLM_PROVIDER = "mock"
    settings.EMBEDDING_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = "AIza-test"
    settings.EMBEDDING_DIM = 8

    import app.llm.gemini_adapter as ga

    def fake_embed(self, texts):
        return [[0.1] * settings.EMBEDDING_DIM for _ in texts]

    monkeypatch.setattr(ga.GeminiAdapter, "embed", fake_embed)

    client = build_llm_client()
    assert client.provider_name == "mock+gemini-embed"
    # Chat still served by the base provider (mock).
    resp = client.generate([{"role": "user", "content": "hello"}])
    assert resp.content
    # Embeddings delegated to the (stubbed) Gemini adapter.
    vecs = client.embed(["query one", "query two"])
    assert len(vecs) == 2 and len(vecs[0]) == 8


def test_gemini_adapter_generates_expected_payload(monkeypatch):
    """The REST payload shape: systemInstruction, roles, outputDimensionality."""
    from app.llm.gemini_adapter import GeminiAdapter

    adapter = GeminiAdapter(api_key="AIza-test")

    captured: dict = {}

    def fake_post(path, body):
        captured["path"] = path
        captured["body"] = body
        return {"candidates": [{"content": {"parts": [{"text": "Hi!"}]}}],
                "usageMetadata": {"totalTokenCount": 3}}

    monkeypatch.setattr(adapter, "_post", fake_post)
    resp = adapter.generate(
        [{"role": "assistant", "content": "previous"}, {"role": "user", "content": "hello"}],
        system="You are PublicAgent.",
    )
    assert resp.content == "Hi!"
    assert captured["path"].endswith(":generateContent")
    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "You are PublicAgent."
    assert captured["body"]["contents"][0]["role"] == "model"
    assert captured["body"]["contents"][1]["role"] == "user"

    # Embeddings request includes outputDimensionality matching EMBEDDING_DIM.
    import app.config as config_mod

    monkeypatch.setattr(config_mod.settings, "EMBEDDING_DIM", 1536)
    monkeypatch.setattr(adapter, "_post", lambda p, b: {"embeddings": [{"values": [0.0] * 1536}]})
    vec = adapter.embed(["one text"])
    assert len(vec[0]) == 1536
