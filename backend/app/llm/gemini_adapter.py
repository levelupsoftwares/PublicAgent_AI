"""Google Gemini adapter — chat via generateContent, embeddings via batchEmbedContents.

Uses Google's REST API directly over httpx (already a project dependency), so no
extra SDK is required and this adapter behaves exactly like the other providers.

Typical .env (Gemini for BOTH chat and embeddings):

    LLM_PROVIDER=gemini
    GEMINI_API_KEY=AIza...
    GEMINI_CHAT_MODEL=gemini-2.0-flash
    GEMINI_EMBEDDING_MODEL=gemini-embedding-001
    EMBEDDING_DIM=1536

Typical .env (keep Groq/Model Studio for chat, Gemini ONLY for embeddings):

    LLM_PROVIDER=groq
    GROQ_API_KEY=gsk_xxx
    EMBEDDING_PROVIDER=gemini
    GEMINI_API_KEY=AIza...
    EMBEDDING_DIM=1536

Notes on dimensions:
- `gemini-embedding-001` produces 3072-dim vectors by default and supports
  Matryoshka truncation via `outputDimensionality` (sensible values: 768,
  1536, 3072). This adapter always requests `outputDimensionality =
  EMBEDDING_DIM` (clamped to >= 768) so the stored width always matches the
  pgvector column / retriever expectation.
- If you change EMBEDDING_DIM after data was ingested, the startup routine
  (`reingest_if_dim_changed`) wipes and re-embeds the knowledge base
  automatically — no manual volume wipe needed for the KB.
- Chat models: any Gemini chat model id works, e.g. gemini-2.0-flash,
  gemini-2.5-flash, gemini-2.5-pro.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

import httpx

from app.config import settings
from app.llm.client import LLMResponse

logger = logging.getLogger("publicagent.llm.gemini")

# gemini-embedding-001 rejects outputDimensionality < 768.
MIN_EMBED_DIM = 768


def _strip_endpoint_suffix(url: str) -> str:
    """Tolerate users pasting a full endpoint URL into GEMINI_BASE_URL."""
    url = url.strip().rstrip("/")
    for suffix in (":generateContent", ":batchEmbedContents", "/v1beta"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url


class GeminiAdapter:
    provider_name = "gemini"

    def __init__(self,
                 api_key: str | None = None,
                 base_url: str | None = None,
                 chat_model: str | None = None,
                 embedding_model: str | None = None):
        self.api_key = (api_key or settings.GEMINI_API_KEY).strip()
        self.base_url = _strip_endpoint_suffix(base_url or settings.GEMINI_BASE_URL)
        self.chat_model = chat_model or settings.GEMINI_CHAT_MODEL
        self.embedding_model = embedding_model or settings.GEMINI_EMBEDDING_MODEL
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is empty — set it in .env or switch LLM_PROVIDER=mock."
            )

    # ------------------------------------------------------------------ chat
    def generate(self, messages: Iterable[dict], *, system: str | None = None,
                 json_mode: bool = False) -> LLMResponse:
        contents: list[dict] = []
        for m in messages:
            role = m.get("role", "user")
            # Gemini only understands "user" and "model" roles.
            grole = "model" if role == "assistant" else "user"
            text = m.get("content", "")
            if isinstance(text, list):  # tolerate OpenAI-style content parts
                text = " ".join(str(p) for p in text)
            contents.append({"role": grole, "parts": [{"text": str(text)}]})

        body: dict[str, Any] = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        gen_cfg: dict[str, Any] = {}
        if json_mode:
            gen_cfg["responseMimeType"] = "application/json"
        if gen_cfg:
            body["generationConfig"] = gen_cfg

        data = self._post(f"models/{self.chat_model}:generateContent", body)
        try:
            content = data["candidates"][0]["content"]["parts"][0].get("text", "")
        except (KeyError, IndexError, TypeError):
            content = ""
            block = data.get("promptFeedback") or data.get("candidates") or {}
            logger.warning("Gemini returned no content: %s", str(block)[:300])
        usage = data.get("usageMetadata", {})
        return LLMResponse(content=content or "", usage=usage)

    # ------------------------------------------------------------- embeddings
    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        dim = int(settings.EMBEDDING_DIM)
        requests = [
            {
                "model": f"models/{self.embedding_model}",
                "content": {"parts": [{"text": t}]},
                # Keep the stored width aligned with EMBEDDING_DIM (pgvector
                # column + brute-force cosine all assume one fixed size).
                "outputDimensionality": max(dim, MIN_EMBED_DIM),
            }
            for t in texts
        ]
        if dim < MIN_EMBED_DIM:
            logger.warning(
                "EMBEDDING_DIM=%s is below gemini-embedding-001's minimum of %s — "
                "requesting %s instead. Update EMBEDDING_DIM to avoid mismatches.",
                dim, MIN_EMBED_DIM, MIN_EMBED_DIM)
        data = self._post("models/"
                          f"{self.embedding_model}:batchEmbedContents",
                          {"requests": requests})
        values = [
            (item.get("values") or item.get("embedding", {}).get("values") or [])
            for item in data.get("embeddings", [])
        ]
        if len(values) != len(texts):
            raise RuntimeError(
                f"Gemini returned {len(values)} embeddings for {len(texts)} inputs.")
        return values

    # ------------------------------------------------------------------ internals
    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}/{path}"
        headers = {"x-goog-api-key": self.api_key,
                   "Content-Type": "application/json"}
        with httpx.Client(timeout=120) as http:
            resp = http.post(url, json=body, headers=headers)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Gemini API error {resp.status_code} on {path}: {resp.text[:400]}")
        return resp.json()
