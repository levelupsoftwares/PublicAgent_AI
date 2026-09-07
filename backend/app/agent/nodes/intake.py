"""Intake nodes: understand_request, classify_issue (+ shared emergency check)."""
from __future__ import annotations

import re

from app.agent.events import (
    INTENT_IDENTIFIED,
    REQUEST_RECEIVED,
)
from app.agent.nodes.base import Services, emit, say, now_iso
from app.agent.state import AgentState

DANGER_RE = re.compile(
    r"\b(kill(ed|ing)?|threaten(ed|ing)?|beat(en|ing)?|tortur(e|ed|ing)|weapon|gun ?(point)?|"
    r"shoot(ing)?|hurt(ed|ing)?|in danger|afraid for my life|fear for my life|abduct(ed|ion)?|"
    r"kidnap(ped|ing)?|rape|violence)\b",
    re.IGNORECASE,
)

EMERGENCY_CARD = {
    "type": "emergency",
    "title": "If anyone is in immediate danger, act now",
    "body": "What you described may involve an immediate safety risk. This assistant can help "
            "you document and file a complaint, but it cannot replace emergency services.",
    "helpline": {"label": "Police emergency helpline (Pakistan)", "number": "15"},
    "actions": [
        "Call the emergency helpline now if anyone is in danger.",
        "Move to a safe location if possible.",
        "Preserve evidence only once it is safe to do so.",
    ],
}


def detect_emergency(text: str) -> bool:
    return bool(DANGER_RE.search(text or ""))


def make_understand_request(services: Services):
    def understand_request(state: AgentState) -> dict:
        updates: dict = {"phase": state.get("phase") or "new"}
        text = (state.get("user_request") or "").strip()
        updates["emergency"] = detect_emergency(text)

        # Initial intent guess from explicit verbs (refined by the options step).
        low = text.lower()
        if re.search(r"\bfile (a )?(formal )?complaint\b|\bwant to (file|complain)\b", low):
            updates["intent"] = "file_complaint"
        elif re.search(r"\bcheck\b|\btrack\b|\bstatus\b", low):
            updates["intent"] = "track"
        else:
            updates.setdefault("intent", "unknown")

        out = emit(state, REQUEST_RECEIVED, {
            "received_at": now_iso(),
            "summary": (text[:120] + "…") if len(text) > 120 else text,
            "emergency_flag": updates["emergency"],
        })
        if updates["emergency"]:
            out.update(say(state, EMERGENCY_CARD["body"], EMERGENCY_CARD))
        return out

    return understand_request


def make_classify_issue(services: Services):
    def classify_issue(state: AgentState) -> dict:
        text = state.get("user_request") or ""
        try:
            resp = services.llm.generate(
                [{"role": "user", "content": text[:1500]}],
                system="[TASK: classify_issue] Classify the citizen's problem. Return JSON: "
                       "{issue_type: police_misconduct|utility_service|general_grievance, "
                       "confidence: 0-1, summary: one neutral sentence, emergency: bool}. "
                       "Be neutral; do not conclude any wrongdoing occurred.",
                json_mode=True,
            )
            data = resp.json() or {}
        except Exception:
            data = {}
        issue_type = data.get("issue_type") if data.get("issue_type") in (
            "police_misconduct", "utility_service", "general_grievance") else "general_grievance"
        summary = data.get("summary") or text[:140]

        out = {
            "issue_type": issue_type,
            "service": issue_type,
        }
        out.update(emit(state, INTENT_IDENTIFIED, {
            "issue_type": issue_type,
            "confidence": data.get("confidence"),
            "summary": summary,
        }))
        return out

    return classify_issue
