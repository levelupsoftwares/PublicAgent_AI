"""RAG retriever — cosine similarity over kb_chunks with source metadata preserved.

Two backends, chosen by DATABASE_URL:
- PostgreSQL + pgvector: native `<=>` cosine distance ordering.
- SQLite (dev/sandbox): embeddings stored as JSON; brute-force cosine in Python.

Both return the same shape: [{"content", "score", "source_ref", "title"}].
"""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import is_postgres
from app.llm.client import get_llm_client
from app.models import KBChunk


def _cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a)) or 1e-9
    dbb = math.sqrt(sum(y * y for y in b)) or 1e-9
    return num / (da * dbb)


def retrieve(db: Session, query: str, k: int | None = None) -> list[dict]:
    k = k or settings.RAG_TOP_K
    if not query.strip():
        return []
    llm = get_llm_client()
    qvec = llm.embed([query])[0]

    if is_postgres():
        try:
            rows = (
                db.execute(
                    select(KBChunk).order_by(KBChunk.embedding.cosine_distance(qvec)).limit(k)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "content": r.content,
                    "score": None,
                    "source_ref": (r.metadata_ or {}).get("source_ref", r.document.source_ref),
                    "title": (r.metadata_ or {}).get("title", r.document.title),
                }
                for r in rows
            ]
        except Exception:
            # e.g. extension missing — fall through to brute force
            pass

    # Brute-force path (SQLite, or pgvector unavailable).
    chunks = db.execute(select(KBChunk)).scalars().all()
    scored: list[tuple[float, KBChunk]] = []
    for ch in chunks:
        emb = ch.embedding
        if not emb:
            continue
        emb = list(emb)
        if len(emb) != len(qvec):
            continue
        scored.append((_cosine(qvec, emb), ch))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [
        {
            "content": ch.content,
            "score": round(score, 4),
            "source_ref": (ch.metadata_ or {}).get("source_ref", ch.document.source_ref),
            "title": (ch.metadata_ or {}).get("title", ch.document.title),
        }
        for score, ch in scored[:k]
    ]
