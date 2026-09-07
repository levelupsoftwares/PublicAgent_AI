"""Agent node core-logic tests (mock LLM; no HTTP)."""
from __future__ import annotations

from app.agent.nodes import (
    make_classify_issue,
    make_collect_information,
    make_prepare_complaint,
    make_submit_complaint,
    make_validate_information,
)
from app.agent.nodes.base import Services
from app.gov.mock_client import MockGovernmentClient
from app.llm.mock_client import MockLLMClient


def _services(db):
    return Services(llm=MockLLMClient(), gov=MockGovernmentClient(),
                    retriever=lambda d, q, k=4: [], db=db)


def test_classify_issue_police(seeded):
    node = make_classify_issue(_services(seeded))
    out = node({"user_request": "A police officer misbehaved with me yesterday"})
    assert out["issue_type"] == "police_misconduct"
    assert out["workflow_events"][0]["event_type"] == "INTENT_IDENTIFIED"


def test_classify_issue_utility(seeded):
    node = make_classify_issue(_services(seeded))
    out = node({"user_request": "My electricity bill is inflated and the meter is faulty"})
    assert out["issue_type"] == "utility_service"


def test_collect_progressive_and_skip(seeded):
    services = _services(seeded)
    state = {
        "issue_type": "police_misconduct",
        "government_data": {"authority": {"authority_id": "PPCA-DEMO"},
                            "requirements": services.gov.get_complaint_requirements("PPCA-DEMO", "police_misconduct")},
        "required_information": [
            {"field": "complainant_name", "label": "Name", "type": "text", "required": True, "status": "missing"},
            {"field": "officer_name", "label": "Officer", "type": "text", "required": False, "status": "missing"},
        ],
        "collected_information": {},
        "asked_fields": [],
        "awaiting_fields": [],
    }
    node = make_collect_information(services)
    out = node(state)
    # Asked the required field first, plus at most one more (≤2 per turn)
    assert out["awaiting_fields"][0] == "complainant_name"
    assert len(out["awaiting_fields"]) <= 2
    card = out["assistant_messages"][0]["structured_payload"]
    assert card["type"] == "information_request"

    # Citizen answers the name; the remaining optional field gets its chance
    out2 = node({**state, "awaiting_fields": ["complainant_name"],
                 "asked_fields": ["complainant_name"],
                 "user_request": "My name is Ahmed Raza"})
    assert out2["collected_information"]["complainant_name"] == "Ahmed Raza"
    assert out2["awaiting_fields"] == ["officer_name"]


def test_validate_missing_required_fails(seeded):
    services = _services(seeded)
    node = make_validate_information(services)
    state = {
        "government_data": {"requirements": services.gov.get_complaint_requirements("PPCA-DEMO", "police_misconduct")},
        "collected_information": {"complainant_name": "A"},
        "asked_fields": [],
    }
    out = node(state)
    assert out["phase"] == "collecting"  # failure re-asks, never proceeds
    assert out["errors"]


def test_submit_hard_gated_on_confirmation(seeded):
    services = _services(seeded)
    node = make_submit_complaint(services)
    state = {"complaint": {"idempotency_key": "x", "category": "c", "department": "d",
                           "description": "", "structured_fields": {}}}
    out = node(state)  # no user_confirmation
    assert "reference_number" not in out
    assert out["assistant_messages"][0]["structured_payload"]["type"] == "notice"

    out2 = node({**state, "user_confirmation": True})
    assert out2["reference_number"].startswith("CMP-")
    assert any(e["event_type"] == "REFERENCE_RECEIVED" for e in out2["workflow_events"])


def test_prepare_lists_unverified(seeded):
    services = _services(seeded)
    node = make_prepare_complaint(services)
    state = {
        "issue_type": "police_misconduct",
        "government_data": {"authority": {"name": "Demo Authority", "jurisdiction": "J"}},
        "collected_information": {"complainant_name": "Ahmed", "officer_name": "__SKIPPED__"},
        "required_information": [
            {"field": "complainant_name", "label": "Your full name", "required": True},
            {"field": "officer_name", "label": "Officer's name (if known)", "required": False},
        ],
        "evidence": [],
    }
    out = node(state)
    card = out["assistant_messages"][0]["structured_payload"]
    assert card["type"] == "review"
    assert out["complaint"]["idempotency_key"]
    skipped = [f for f in card["fields"] if f["skipped"]]
    assert skipped and skipped[0]["field"] == "officer_name"
