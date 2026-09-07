"""LangGraph graph assembly (spec §7).

Primary complaint graph (fresh flow):
  understand_request → classify_issue → identify_authority →
  retrieve_official_information → analyze_available_data → present_options → END

Filing continuation:
  collect_information → validate_information → prepare_complaint →
  request_confirmation → submit_complaint → store_complaint → schedule_followup → END

Government-message graph:
  analyze_user_message → detect_government_message → extract_reference →
  retrieve_complaint → analyze_status → update_complaint → explain_to_user → END

All paths live in ONE compiled StateGraph; a conditional edge from START routes to
the right node from the persisted conversation phase, keeping statefulness across
chat turns while preserving the exact node names and edge sequences above. One
extra node, present_guidance, implements §2's Understand-My-Options behaviour
(documented in DECISIONS.md). A third service category is a data change, not a
structural one — classification + requirements are parameterised by issue_type.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    make_analyze_available_data,
    make_analyze_status,
    make_analyze_user_message,
    make_classify_issue,
    make_collect_information,
    make_detect_government_message,
    make_explain_to_user,
    make_extract_reference,
    make_identify_authority,
    make_prepare_complaint,
    make_present_guidance,
    make_present_options,
    make_request_confirmation,
    make_retrieve_complaint,
    make_retrieve_official_information,
    make_schedule_followup,
    make_store_complaint,
    make_submit_complaint,
    make_understand_request,
    make_update_complaint,
    make_validate_information,
)
from app.agent.nodes.base import Services
from app.agent.state import AgentState


def build_agent_graph(services: Services):
    """Compile the agent graph bound to a request-scoped Services container."""
    g = StateGraph(AgentState)

    # --- primary complaint graph nodes (exact names from the spec) ---
    g.add_node("understand_request", make_understand_request(services))
    g.add_node("classify_issue", make_classify_issue(services))
    g.add_node("identify_authority", make_identify_authority(services))
    g.add_node("retrieve_official_information", make_retrieve_official_information(services))
    g.add_node("analyze_available_data", make_analyze_available_data(services))
    g.add_node("present_options", make_present_options(services))
    g.add_node("present_guidance", make_present_guidance(services))
    g.add_node("collect_information", make_collect_information(services))
    g.add_node("validate_information", make_validate_information(services))
    g.add_node("prepare_complaint", make_prepare_complaint(services))
    g.add_node("request_confirmation", make_request_confirmation(services))
    g.add_node("submit_complaint", make_submit_complaint(services))
    g.add_node("store_complaint", make_store_complaint(services))
    g.add_node("schedule_followup", make_schedule_followup(services))

    # --- government-message graph nodes (exact names from the spec) ---
    g.add_node("analyze_user_message", make_analyze_user_message(services))
    g.add_node("detect_government_message", make_detect_government_message(services))
    g.add_node("extract_reference", make_extract_reference(services))
    g.add_node("retrieve_complaint", make_retrieve_complaint(services))
    g.add_node("analyze_status", make_analyze_status(services))
    g.add_node("update_complaint", make_update_complaint(services))
    g.add_node("explain_to_user", make_explain_to_user(services))

    # --- edges (exact sequences from the spec) ---
    g.add_edge("understand_request", "classify_issue")
    g.add_edge("classify_issue", "identify_authority")
    g.add_edge("identify_authority", "retrieve_official_information")
    g.add_edge("analyze_available_data", "present_options")
    g.add_edge("present_options", END)
    g.add_edge("present_guidance", END)
    # Guidance branch forks AFTER retrieval: fresh flow continues to requirements
    # analysis; the guidance branch goes straight to present_guidance.
    g.add_conditional_edges(
        "retrieve_official_information",
        _after_retrieval,
        {"fresh": "analyze_available_data", "guidance": "present_guidance"},
    )

    g.add_conditional_edges(
        "collect_information",
        _after_collect,
        {"validate": "validate_information", "wait": END},
    )
    g.add_conditional_edges(
        "validate_information",
        _after_validate,
        {"prepare": "prepare_complaint", "wait": END},
    )
    g.add_edge("prepare_complaint", "request_confirmation")
    g.add_conditional_edges(
        "request_confirmation",
        _after_confirmation,
        {"submit": "submit_complaint", "wait": END},
    )
    g.add_edge("submit_complaint", "store_complaint")
    g.add_edge("store_complaint", "schedule_followup")
    g.add_edge("schedule_followup", END)

    # Government-message path
    g.add_edge("analyze_user_message", "detect_government_message")
    g.add_edge("detect_government_message", "extract_reference")
    g.add_edge("extract_reference", "retrieve_complaint")
    g.add_edge("retrieve_complaint", "analyze_status")
    g.add_edge("analyze_status", "update_complaint")
    g.add_edge("update_complaint", "explain_to_user")
    g.add_edge("explain_to_user", END)

    # --- conditional entry point ---
    g.add_conditional_edges(
        START,
        _route_entry,
        {
            "fresh": "understand_request",
            "guidance": "retrieve_official_information",
            "collect": "collect_information",
            "confirm": "request_confirmation",
            "gov_message": "analyze_user_message",
        },
    )
    return g.compile()


def _looks_like_gov_message(text: str) -> bool:
    from app.parsing.gov_message_parser import looks_like_government_message

    try:
        looks, _ = looks_like_government_message(text)
        return looks
    except Exception:
        return False


GUIDANCE_PHRASES = [
    r"\bunderstand (my |the )?options\b", r"\bwhat are my options\b", r"\bnot sure\b",
    r"\bdon.?t know what to do\b", r"\bguide me\b", r"\bexplain my options\b",
    r"\bwhat (can|should) i do\b", r"\bhelp me understand\b",
]


def wants_guidance(text: str) -> bool:
    import re

    low = (text or "").lower().strip()
    return any(re.search(p, low) for p in GUIDANCE_PHRASES)


def _route_entry(state: AgentState) -> str:
    """Pick the sub-graph for this turn from the persisted phase + new message.

    The chat orchestrator pre-computes guidance_requested / phase changes /
    user_confirmation from structured actions before invoking, so the router only
    reads state.
    """
    text = state.get("user_request") or ""
    phase = state.get("phase") or "new"

    # A pasted government SMS/email takes priority — at any point in the journey.
    if text and _looks_like_gov_message(text):
        return "gov_message"
    if state.get("guidance_requested"):
        return "guidance"
    if phase == "collecting":
        return "collect"
    if phase == "awaiting_confirmation":
        return "confirm"
    if phase == "options_presented" and _wants_to_file(text):
        return "collect"
    return "fresh"


def _after_retrieval(state: AgentState) -> str:
    return "guidance" if state.get("guidance_requested") else "fresh"


def _wants_to_file(text: str) -> bool:
    import re

    low = (text or "").lower().strip()
    patterns = [
        r"^file\b", r"\bfile (a|the)? ?(formal )?complaint\b", r"\bi want to file\b",
        r"\breport the incident\b", r"\bplease file\b", r"\blet.s file\b",
        r"\bstart (a|the)? ?complaint\b", r"^submit\b",
    ]
    return any(re.search(p, low) for p in patterns)


def _after_collect(state: AgentState) -> str:
    # collect_information leaves awaiting_fields EMPTY when everything required is
    # handled; otherwise it asked a question this turn and we wait for the answer.
    asked = state.get("awaiting_fields") or []
    collected = state.get("collected_information") or {}
    info = {f["field"]: f for f in (state.get("required_information") or [])}
    for name in asked:
        f = info.get(name)
        if f and f["required"] and collected.get(name) in (None, ""):
            return "wait"
    return "validate"


def _after_validate(state: AgentState) -> str:
    if state.get("phase") == "ready_for_review":
        return "prepare"
    return "wait"  # validation failed → fields re-asked, wait for the citizen


def _after_confirmation(state: AgentState) -> str:
    return "submit" if state.get("user_confirmation") else "wait"
