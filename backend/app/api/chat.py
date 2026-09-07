"""Chat orchestrator — the bridge between HTTP and the LangGraph agent.

Per turn:
1. Load/create the conversation; restore the persisted AgentState.
2. Append the citizen's message; apply any structured action (option/skip/confirm).
3. Invoke the compiled graph with a START conditional-edge router.
4. Persist produced assistant messages + workflow events + the updated state.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agent.graph import build_agent_graph, wants_guidance, _looks_like_gov_message
from app.agent.nodes.base import Services
from app.agent.state import AgentState
from app.config import settings
from app.llm.client import get_llm_client
from app.models import Conversation, Message, User
from app.rag.retriever import retrieve
from app.gov.client import get_gov_client

logger = logging.getLogger("publicagent.chat")

VOLATILE_KEYS = {"user_request", "guidance_requested", "guidance_mode", "user_confirmation",
                 "errors", "assistant_messages", "workflow_events"}


def _new_conversation(db: Session, user: User, first_message: str) -> Conversation:
    title = (first_message.strip()[:60] + "…") if len(first_message.strip()) > 60 \
        else (first_message.strip() or "New conversation")
    conv = Conversation(user_id=user.id, title=title, agent_state={})
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _apply_action(state: AgentState, action: dict | None, text: str) -> None:
    """Translate structured UI actions into state mutations before the graph runs."""
    if not action:
        return
    kind = action.get("type")
    if kind == "option":
        option = action.get("option")
        if option in ("file", "report"):
            state["phase"] = "collecting"
            state["intent"] = "file_complaint" if option == "file" else "report"
        elif option in ("understand", "not_sure"):
            # Guidance is an options/tracking-phase behaviour; never derail an
            # in-progress collection or confirmation.
            if state.get("phase") not in ("collecting", "awaiting_confirmation"):
                state["guidance_requested"] = True
                state["guidance_mode"] = "understand" if option == "understand" else "not_sure"
                state["phase"] = state.get("phase") or "options_presented"
    elif kind == "skip":
        field = action.get("field")
        if field:
            info = state.get("required_information") or []
            for f in info:
                if f["field"] == field:
                    f["status"] = "skipped"
            state["required_information"] = info
            collected = state.get("collected_information") or {}
            collected[field] = "__SKIPPED__"
            state["collected_information"] = collected
    elif kind == "confirm":
        state["user_confirmation"] = bool(action.get("value", True))
        if not action.get("value", True):
            state["phase"] = "collecting"  # Go Back → revisit collection/review
    elif kind == "cancel":
        state["phase"] = "collecting"


def run_chat_turn(
    db: Session,
    user: User,
    conversation_id: str | None,
    content: str,
    action: dict | None,
) -> tuple[str, list[Message], list[dict], str]:
    """Returns (conversation_id, new_messages, workflow_events, phase)."""
    text = (content or "").strip()
    if not text and not action:
        raise ValueError("Empty message")

    # 1) Conversation
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if conv is None or conv.user_id != user.id:
            raise LookupError("Conversation not found")
    else:
        conv = _new_conversation(db, user, text or "New conversation")

    # 1b) Already-submitted complaint: a re-confirm is a friendly no-op.
    state0: AgentState = dict(conv.agent_state or {})
    if (state0.get("phase") == "tracking" and action and action.get("type") == "confirm"):
        msg = Message(
            conversation_id=conv.id, role="assistant",
            content="This complaint was already submitted — it's being tracked. You'll "
                    "receive a notification here when the status changes.",
            structured_payload={
                "type": "notice", "level": "info", "title": "Already submitted",
                "body": "No duplicate was created. Use the dashboard to follow the timeline.",
            },
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return conv.id, [msg], [], "tracking"

    # 2) Restore state
    state: AgentState = dict(conv.agent_state or {})
    state.setdefault("conversation_id", conv.id)
    state["user_id"] = user.id
    state["conversation_id"] = conv.id
    if not state.get("initial_request") and text:
        state["initial_request"] = text[:800]

    # Record the citizen's message (display-friendly for structured actions).
    if action:
        kind = action.get("type")
        if kind == "option":
            labels = {"file": "File a Formal Complaint", "report": "Report the Incident",
                      "understand": "Understand My Options", "not_sure": "I'm Not Sure What To Do"}
            display = labels.get(action.get("option"), str(action))
        elif kind == "skip":
            fields = {f["field"]: f["label"] for f in (state.get("required_information") or [])}
            display = f"Skipped: {fields.get(action.get('field'), action.get('field'))}"
        elif kind == "confirm":
            display = "Confirm & Submit" if action.get("value", True) else "Go back"
        else:
            display = str(action)
        user_msg = Message(conversation_id=conv.id, role="user", content=display)
    else:
        user_msg = Message(conversation_id=conv.id, role="user", content=text)
    db.add(user_msg)

    # 3) Pre-apply structured actions + phase intents
    state["user_request"] = text
    if state.get("phase") in ("tracking", "ready_for_review") and text \
            and not _looks_like_gov_message(text):
        state["guidance_requested"] = True  # post-submission questions → guidance
    elif state.get("phase") == "options_presented" and text and not action \
            and wants_guidance(text) and not _looks_like_gov_message(text):
        state["guidance_requested"] = True
    _apply_action(state, action, text)

    # 4) Invoke the agent graph
    services = Services(
        llm=get_llm_client(),
        gov=get_gov_client(),
        retriever=retrieve,
        db=db,
    )
    graph = build_agent_graph(services)
    try:
        result = graph.invoke(state, {"recursion_limit": 25})
    except Exception:
        logger.exception("Agent graph failed")
        db.rollback()
        raise

    # 5) Persist results
    conv.agent_state = {k: v for k, v in result.items() if k not in VOLATILE_KEYS}
    conv.updated_at = datetime.now(timezone.utc)
    if result.get("errors"):
        logger.warning("Agent errors on conv %s: %s", conv.id, result["errors"][:3])

    produced = result.get("assistant_messages") or []
    events = result.get("workflow_events") or []
    new_messages: list[Message] = []
    for m in produced:
        msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=m.get("content", ""),
            structured_payload=m.get("structured_payload"),
            workflow_events=None,
        )
        db.add(msg)
        new_messages.append(msg)
    # Stamp the events onto the LAST assistant message for easy frontend playback.
    if new_messages and events:
        new_messages[-1].workflow_events = events
    db.commit()
    for m in new_messages:
        db.refresh(m)
    db.refresh(conv)
    return conv.id, new_messages, events, conv.agent_state.get("phase", "new")
