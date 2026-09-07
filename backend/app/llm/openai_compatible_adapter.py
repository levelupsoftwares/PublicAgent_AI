"""Generic OpenAI-compatible adapter (fallback provider, spec §4)."""
from __future__ import annotations

from typing import Any, Iterable

import httpx

from app.config import settings
from app.llm.client import LLMResponse


class OpenAICompatibleAdapter:
    provider_name = "openai_compatible"

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, embedding_model: str | None = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.base_url = (base_url or settings.OPENAI_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL_NAME
        self.embedding_model = embedding_model or settings.EMBEDDING_MODEL_NAME
        if not self.api_key or not self.base_url:
            raise RuntimeError(
                "OPENAI_API_KEY / OPENAI_BASE_URL are required for LLM_PROVIDER=openai_compatible."
            )

    def generate(self, messages: Iterable[dict], *, system: str | None = None,
                 json_mode: bool = False) -> LLMResponse:
        payload_messages: list[dict] = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(dict(m) for m in messages)
        body: dict[str, Any] = {"model": self.model, "messages": payload_messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        with httpx.Client(timeout=60) as http:
            resp = http.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"].get("content") or "",
            tool_calls=choice["message"].get("tool_calls") or [],
            usage=data.get("usage", {}),
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        with httpx.Client(timeout=60) as http:
            resp = http.post(
                f"{self.base_url}/embeddings",
                json={"model": self.embedding_model, "input": texts},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
        items = sorted(data["data"], key=lambda d: d["index"])
        return [item["embedding"] for item in items]
