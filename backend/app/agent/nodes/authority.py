"""Authority + knowledge nodes: identify_authority, retrieve_official_information,
analyze_available_data, and present_options."""
from __future__ import annotations

from app.agent.events import (
    AUTHORITY_IDENTIFIED,
    OFFICIAL_DATA_RETRIEVED,
    REQUIREMENTS_IDENTIFIED,
)
from app.agent.nodes.base import Services, emit, say
from app.agent.state import AgentState

ISSUE_LABELS = {
    "police_misconduct": "police misconduct",
    "utility_service": "a utility service problem",
    "general_grievance": "a public service grievance",
}

OPTIONS_CARD = {
    "type": "options",
    "title": "What would you like to do?",
    "subtitle": "Choose one — you can change your mind at any time.",
    "options": [
        {"id": "understand", "label": "Understand My Options",
         "description": "Neutral, plain-language guidance about how issues like yours are usually handled.",
         "icon": "compass"},
        {"id": "report", "label": "Report the Incident",
         "description": "Get the event on record without starting a formal complaint process.",
         "icon": "megaphone"},
        {"id": "file", "label": "File a Formal Complaint",
         "description": "I'll collect only the required information, show you a review, and submit after your explicit confirmation.",
         "icon": "file-signature"},
        {"id": "not_sure", "label": "I'm Not Sure What To Do",
         "description": "That's okay — describe your situation and we'll figure out the next step together.",
         "icon": "help-circle"},
    ],
}


def make_identify_authority(services: Services):
    def identify_authority(state: AgentState) -> dict:
        issue_type = state.get("issue_type") or "general_grievance"
        location = (state.get("collected_information") or {}).get("location")
        try:
            result = services.gov.find_authority(issue_type, location)
        except Exception:
            result = {"authority": {}, "source": "mock"}
        auth = result.get("authority", {}) or {}
        out = {
            "government_data": {**(state.get("government_data") or {}), "authority": auth},
            "department": auth.get("name", ""),
            "jurisdiction": auth.get("jurisdiction", ""),
        }
        out.update(emit(state, AUTHORITY_IDENTIFIED, {
            "authority": auth.get("name"), "jurisdiction": auth.get("jurisdiction"),
            "source": result.get("source", "mock"),
        }))
        return out

    return identify_authority


def make_retrieve_official_information(services: Services):
    def retrieve_official_information(state: AgentState) -> dict:
        issue_type = state.get("issue_type") or "general_grievance"
        query = f"{state.get('user_request', '')} {ISSUE_LABELS.get(issue_type, '')} complaint process requirements"
        try:
            chunks = services.retriever(services.db, query, k=4)
        except Exception:
            chunks = []
        out = {"official_context": chunks}
        out.update(emit(state, OFFICIAL_DATA_RETRIEVED, {
            "chunks": [{"title": c.get("title"), "source_ref": c.get("source_ref")} for c in chunks],
        }))
        return out

    return retrieve_official_information


def make_analyze_available_data(services: Services):
    def analyze_available_data(state: AgentState) -> dict:
        issue_type = state.get("issue_type") or "general_grievance"
        auth = (state.get("government_data") or {}).get("authority", {}) or {}
        try:
            req = services.gov.get_complaint_requirements(auth.get("authority_id", ""), issue_type)
        except Exception:
            req = {"fields": [], "source": "mock"}
        required_information = [
            {
                "field": f["field"], "label": f["label"], "type": f.get("type", "text"),
                "required": bool(f.get("required")), "status": "missing",
            }
            for f in req.get("fields", [])
        ]
        out = {
            "government_data": {**(state.get("government_data") or {}),
                                "requirements": req,
                                "requirements_source": req.get("source", "mock")},
            "required_information": required_information,
        }
        out.update(emit(state, REQUIREMENTS_IDENTIFIED, {
            "category": issue_type,
            "required_fields": [f["field"] for f in required_information if f["required"]],
            "optional_fields": [f["field"] for f in required_information if not f["required"]],
        }))
        return out

    return analyze_available_data


def make_present_options(services: Services):
    def present_options(state: AgentState) -> dict:
        issue_type = state.get("issue_type") or "general_grievance"
        auth = (state.get("government_data") or {}).get("authority", {}) or {}
        label = ISSUE_LABELS.get(issue_type, issue_type)
        prose = (
            f"Thank you for telling me about this. What you described sounds like it may be "
            f"{label}. I'm not a court and I'm not deciding anything — I can only help you "
            f"understand typical options and, if you choose, prepare a complaint. "
            f"Based on the (demo) guidance I retrieved, issues like this are usually handled by "
            f"an authority such as {auth.get('name') or 'a complaints authority'} "
            f"(demo data — not a verified real institution)."
        )
        sources = [
            {"title": c.get("title"), "source_ref": c.get("source_ref")}
            for c in (state.get("official_context") or [])[:4]
        ]
        card = dict(OPTIONS_CARD)
        card["issue_type"] = issue_type
        card["authority"] = {"name": auth.get("name"), "jurisdiction": auth.get("jurisdiction")}
        card["sources"] = sources
        card["data_labels"] = {
            "reported_by_you": "What you reported — not verified",
            "mock_official": "Demo / mock government data",
        }
        out = say(state, prose, card)
        if sources:
            out["assistant_messages"] = out["assistant_messages"] + [{
                "content": "",
                "structured_payload": {
                    "type": "source_citations", "sources": sources,
                    "note": "Retrieved from the demo knowledge base (illustrative guidance).",
                },
            }]
        out["phase"] = "options_presented"
        from app.agent.events import make_event

        out["workflow_events"] = [make_event("OPTIONS_PRESENTED", {"issue_type": issue_type})]
        return out

    return present_options
