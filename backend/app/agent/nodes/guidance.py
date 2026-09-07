"""Guidance node — serves the "Understand My Options" / "I'm Not Sure" branches.

Added to the spec's node list to implement §2's Understand-My-Options behaviour
(neutral, RAG-grounded guidance with citations). Documented in DECISIONS.md.
"""
from __future__ import annotations

from app.agent.events import make_event
from app.agent.nodes.base import Services, say
from app.agent.state import AgentState

ISSUE_LABELS = {
    "police_misconduct": "police misconduct",
    "utility_service": "a utility service problem",
    "general_grievance": "a public service grievance",
}


def make_present_guidance(services: Services):
    def present_guidance(state: AgentState) -> dict:
        mode = state.get("guidance_mode") or "understand"
        issue_type = state.get("issue_type") or "general_grievance"
        auth = (state.get("government_data") or {}).get("authority", {}) or {}
        context = state.get("official_context") or []
        label = ISSUE_LABELS.get(issue_type, issue_type)

        def src_text(pattern: str) -> str:
            for c in context:
                if pattern in (c.get("content", "") + c.get("title", "")).lower() or pattern in (c.get("source_ref") or ""):
                    return c.get("content", "")[:600]
            return context[0]["content"][:600] if context else ""

        card = {
            "type": "guidance",
            "title": "Understanding your options" if mode == "understand" else "That's okay — here's the picture",
            "issue_type": issue_type,
            "sections": [
                {"heading": "What this kind of issue usually is",
                 "body": f"What you reported sounds like it may be {label}. This is a neutral "
                         f"observation, not a legal conclusion — only an authority can "
                         f"determine what actually happened."},
                {"heading": "Who typically handles it",
                 "body": f"{auth.get('name') or 'A complaints authority'} "
                         f"({'demo data — not a verified real institution'}). "
                         f"{auth.get('description', '')}".strip()},
                {"heading": "What information / evidence is useful to preserve",
                 "body": src_text("evidence") or
                         "Write down the date, time and place while fresh; keep original "
                         "documents and unedited photos; note names or badge numbers if you "
                         "saw them; and identify possible witnesses or CCTV early."},
                {"heading": "What the general filing process looks like",
                 "body": src_text("filing") or
                         "Identify the authority, gather facts, describe the incident, submit, "
                         "receive a reference number, and respond to follow-ups promptly."},
                {"heading": "What happens after filing",
                 "body": src_text("after submission") or
                         "The authority acknowledges with a reference number, may request "
                         "additional documents, assigns an inquiry officer, and communicates "
                         "the outcome against your reference number."},
            ],
            "sources": [{"title": c.get("title"), "source_ref": c.get("source_ref")}
                        for c in context[:4]],
            "disclaimer": "Neutral, informational guidance only — not legal advice, not a "
                          "legal conclusion. All guidance is illustrative demo content.",
        }
        if mode == "understand":
            prose = ("Here's a neutral overview of how this kind of situation is usually "
                     "handled. Take your time — none of this commits you to anything, and "
                     "filing is only one of the paths available.")
        else:
            prose = ("Being unsure is completely normal. Here's the lay of the land — when "
                     "you're ready, I can help you file a formal complaint, or we can just "
                     "talk through what happened.")
        out = say(state, prose, card)
        out["assistant_messages"] = out["assistant_messages"] + [{
            "content": "",
            "structured_payload": {
                "type": "source_citations",
                "sources": card["sources"],
                "note": "Retrieved from the demo knowledge base (illustrative guidance).",
            },
        }]
        out["phase"] = state.get("phase") if state.get("phase") in (
            "collecting", "awaiting_confirmation", "tracking") else "options_presented"
        out["guidance_mode"] = None
        out["workflow_events"] = [make_event("GUIDANCE_PROVIDED", {"issue_type": issue_type})]
        return out

    return present_guidance
