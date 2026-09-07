"""Groq LLM adapter + OpenRouter embedding adapter.

Uses Groq's OpenAI-compatible endpoint for chat completions and OpenRouter's
OpenAI-compatible endpoint for embeddings. Both keys are required (the
LLMClient interface exposes both `generate` and `embed` so this adapter
composes two providers behind one facade).

Typical .env:

    LLM_PROVIDER=groq
    GROQ_API_KEY=gsk_xxx
    GROQ_MODEL_NAME=qwen/qwen3-32b
    OPENROUTER_API_KEY=sk-or-v1-xxx
    OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
    EMBEDDING_MODEL_NAME=nvidia/nemotron-3-embed-1b:free
    EMBEDDING_DIM=1024

If the embedding model returns a different dimension than EMBEDDING_DIM, set
EMBEDDING_DIM to match (and wipe the database so the pgvector column is
recreated at the right width on first boot).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

import httpx

from app.config import settings
from app.llm.client import LLMResponse

logger = logging.getLogger("publicagent.llm.groq")


def _strip_endpoint_suffix(url: str) -> str:
    """Tolerate users pasting the full endpoint URL in .env."""
    url = url.strip().rstrip("/")
    for suffix in ("/chat/completions", "/embeddings"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url


class GroqAdapter:
    provider_name = "groq"

    def __init__(self,
                 groq_api_key: str | None = None,
                 groq_base_url: str | None = None,
                 groq_model: str | None = None,
                 openrouter_api_key: str | None = None,
                 openrouter_base_url: str | None = None,
                 embedding_model: str | None = None):
        # --- chat (Groq) ---
        self.api_key = groq_api_key or settings.GROQ_API_KEY
        self.base_url = _strip_endpoint_suffix(
            groq_base_url or settings.GROQ_BASE_URL)
        self.model = groq_model or settings.GROQ_MODEL_NAME

        # --- embeddings (OpenRouter) ---
        self.embedding_api_key = openrouter_api_key or settings.OPENROUTER_API_KEY
        self.embedding_base_url = _strip_endpoint_suffix(
            openrouter_base_url or settings.OPENROUTER_BASE_URL)
        self.embedding_model = embedding_model or settings.EMBEDDING_MODEL_NAME

        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is empty — set it in .env or switch LLM_PROVIDER=mock."
            )
        if not self.embedding_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is empty — embeddings require an OpenRouter key. "
                "Set it in .env or switch LLM_PROVIDER=mock."
            )

    # -- LLM API ----------------------------------------------------------
    def generate(self, messages: Iterable[dict], *, system: str | None = None,
                 json_mode: bool = False) -> LLMResponse:
        payload_messages: list[dict] = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(dict(m) for m in messages)
        body: dict[str, Any] = {"model": self.model, "messages": payload_messages}
        if json_mode:
            # Groq supports json_object response_format on most chat models.
            body["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=60) as http:
            resp = http.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"].get("content") or "",
            tool_calls=choice["message"].get("tool_calls") or [],
            usage=data.get("usage", {}),
        )

    # -- Embeddings API (OpenRouter) -------------------------------------
    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {
            "Authorization": f"Bearer {self.embedding_api_key}",
            "Content-Type": "application/json",
        }
        body = {"model": self.embedding_model, "input": texts}
        with httpx.Client(timeout=120) as http:
            resp = http.post(
                f"{self.embedding_base_url}/embeddings",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        items = sorted(data["data"], key=lambda d: d["index"])
        return [item["embedding"] for item in items]
