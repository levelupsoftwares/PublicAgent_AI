"""Government message parser tests (regex + heuristics)."""
from __future__ import annotations

from app.parsing.gov_message_parser import (
    extract_reference,
    guess_status,
    looks_like_government_message,
    parse_government_message,
)

SMS = ("Police Complaints Authority: Complaint CMP-2026-001928 requires additional "
       "documents. Please submit a copy of your CNIC within 3 days.")


def test_reference_regex():
    assert extract_reference(SMS) == "CMP-2026-001928"
    assert extract_reference("no reference here") is None


def test_looks_government():
    looks, conf = looks_like_government_message(SMS)
    assert looks and conf > 0.4
    looks2, conf2 = looks_like_government_message("hey whats up lol")
    assert not looks2


def test_status_guess():
    assert guess_status(SMS) == "additional_info_required"
    assert guess_status("Your complaint has been resolved. Thank you.") == "resolved"
    assert guess_status("We received your complaint") == "received"
    assert guess_status("The case is under review by the officer") == "under_review"


def test_full_parse():
    a = parse_government_message(SMS, use_llm=False)
    assert a.reference_number == "CMP-2026-001928"
    assert a.status == "additional_info_required"
    assert a.required_action and "documents" in a.required_action.lower()
    assert "not independently verified" not in a.explanation  # label lives in the UI layer
    assert a.explanation  # plain-language explanation exists
