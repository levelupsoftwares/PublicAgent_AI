"""Shared node context — services injected into node factories so nodes stay
unit-testable (swap mocks in) and never import providers directly."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agent.events import make_event
from app.agent.state import AgentState


@dataclass
class Services:
    llm: object                  # LLMClient
    gov: object                  # GovernmentServiceClient
    retriever: object            # callable(db, query, k) -> list[dict]
    db: Session                  # request-scoped session


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(state: AgentState, event_type: str, payload: dict | None = None) -> dict:
    return {"workflow_events": [make_event(event_type, payload)]}


def say(state: AgentState, content: str, card: dict | None = None) -> dict:
    msg = {"content": content}
    if card:
        msg["structured_payload"] = card
    return {"assistant_messages": [msg]}


def add_error(state: AgentState, message: str) -> dict:
    return {"errors": [message]}


def mask_sensitive(value: str | None) -> str | None:
    """Partial masking for CNIC-like numbers / badge numbers in transcripts."""
    if not value or not isinstance(value, str):
        return value
    digits = sum(ch.isdigit() for ch in value)
    if digits >= 8:
        return value[:2] + "*" * max(len(value) - 4, 2) + value[-2:]
    return value
