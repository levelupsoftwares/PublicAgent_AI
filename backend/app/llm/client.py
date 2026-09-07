"""LLMClient abstraction — agent nodes NEVER call a provider SDK directly.

Providers (selected via LLM_PROVIDER env):
  - model_studio      Alibaba Cloud Model Studio (Qwen, OpenAI-compatible endpoint)
  - openai_compatible any generic OpenAI-compatible endpoint
  - groq              Groq (chat) + OpenRouter (embeddings) — mixed-provider mode
  - mock              deterministic offline engine used for the sandboxed demo/tests
                      (no key required) — clearly documented in DECISIONS.md
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Protocol


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)

    def json(self) -> Optional[dict]:
        """Best-effort JSON extraction from a model reply."""
        text = self.content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    return None
        return None


class LLMClient(Protocol):
    def generate(
        self,
        messages: Iterable[dict],
        *,
        system: str | None = None,
        json_mode: bool = False,
    ) -> LLMResponse: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def build_llm_client() -> LLMClient:
    import logging

    from app.config import settings

    logger = logging.getLogger("publicagent.llm")
    provider = settings.LLM_PROVIDER.lower().strip()

    # Safety net: a remote provider with no credentials would crash the app on
    # first use. Fall back to the deterministic offline mock instead — the demo
    # keeps working everywhere, and the UI labels all outputs accordingly.
    if provider == "model_studio" and not settings.DASHSCOPE_API_KEY.strip():
        logger.warning(
            "LLM_PROVIDER=model_studio but DASHSCOPE_API_KEY is empty — "
            "falling back to the offline mock engine. Set the key in .env "
            "to use Qwen.")
        provider = "mock"
    if provider == "openai_compatible" and not (
            settings.OPENAI_API_KEY.strip() or settings.OPENAI_BASE_URL.strip()):
        logger.warning(
            "LLM_PROVIDER=openai_compatible but neither OPENAI_API_KEY nor "
            "OPENAI_BASE_URL is set — falling back to the offline mock engine.")
        provider = "mock"
    if provider == "groq":
        if not settings.GROQ_API_KEY.strip():
            logger.warning(
                "LLM_PROVIDER=groq but GROQ_API_KEY is empty — "
                "falling back to the offline mock engine. Set the key in .env "
                "to use Groq + Qwen.")
            provider = "mock"
        elif not settings.OPENROUTER_API_KEY.strip():
            logger.warning(
                "LLM_PROVIDER=groq but OPENROUTER_API_KEY is empty — embeddings "
                "are unavailable. Falling back to the offline mock engine. "
                "Set OPENROUTER_API_KEY in .env to enable embeddings.")
            provider = "mock"

    if provider == "model_studio":
        from app.llm.model_studio_adapter import ModelStudioAdapter

        return ModelStudioAdapter()
    if provider == "openai_compatible":
        from app.llm.openai_compatible_adapter import OpenAICompatibleAdapter

        return OpenAICompatibleAdapter()
    if provider == "groq":
        from app.llm.groq_adapter import GroqAdapter

        return GroqAdapter()
    from app.llm.mock_client import MockLLMClient

    return MockLLMClient()


# Module-level singleton (rebuilt lazily so tests can swap providers).
_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = build_llm_client()
    return _client


def set_llm_client(client: LLMClient | None) -> None:
    global _client
    _client = client
