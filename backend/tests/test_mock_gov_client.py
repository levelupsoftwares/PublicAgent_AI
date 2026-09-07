"""MockGovernmentClient behaviour tests (incl. demo status progression)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_submit_returns_reference_and_idempotent(mock_gov):
    payload = {"idempotency_key": "abc-123", "category": "police_misconduct",
               "department": "X", "description": "d", "structured_fields": {}}
    r1 = mock_gov.submit_complaint(payload)
    r2 = mock_gov.submit_complaint(payload)
    assert r1["reference_number"].startswith("CMP-")
    assert r1["reference_number"] == r2["reference_number"]
    assert r2["duplicate"] is True
    assert r1["source"] == "mock"


def test_status_not_found(mock_gov):
    r = mock_gov.get_complaint_status("CMP-2026-999999")
    assert r["found"] is False


def test_status_progression_over_time(mock_gov):
    ref = mock_gov.submit_complaint({"idempotency_key": "k1", "category": "c",
                                     "department": "d", "description": "x",
                                     "structured_fields": {}})["reference_number"]
    assert mock_gov.get_complaint_status(ref)["status"] == "submitted"
    # Simulate elapsed time by writing a case with an older submitted_at.
    mock_gov.seed_case(ref + "-A", submitted_at=datetime.now(timezone.utc) - timedelta(seconds=45),
                       category="c", department="d", jurisdiction=None,
                       description="x", structured_fields={})
    assert mock_gov.get_complaint_status(ref + "-A")["status"] == "received"
    mock_gov.seed_case(ref + "-B", submitted_at=datetime.now(timezone.utc) - timedelta(seconds=120),
                       category="c", department="d", jurisdiction=None,
                       description="x", structured_fields={})
    assert mock_gov.get_complaint_status(ref + "-B")["status"] == "under_review"


def test_force_advance_and_requirements(mock_gov):
    ref = mock_gov.submit_complaint({"idempotency_key": "k2", "category": "c",
                                     "department": "d", "description": "x",
                                     "structured_fields": {}})["reference_number"]
    r = mock_gov.force_advance(ref)
    assert r["status"] == "received"
    req = mock_gov.get_complaint_requirements("PPCA-DEMO", "police_misconduct")
    names = [f["field"] for f in req["fields"]]
    assert "officer_name" in names
    officer = next(f for f in req["fields"] if f["field"] == "officer_name")
    assert officer["required"] is False  # optional fields are skippable


def test_validate_citizen_information(mock_gov):
    req = mock_gov.get_complaint_requirements("PPCA-DEMO", "police_misconduct")
    ok = mock_gov.validate_citizen_information(
        {"complainant_name": "A", "incident_date": "2026-01-01", "location": "x",
         "police_station": "y", "description": "z", "complainant_phone": "0300-1234567"},
        req)
    assert ok["valid"] is True
    bad = mock_gov.validate_citizen_information({"complainant_name": "A"}, req)
    assert bad["valid"] is False
    assert any(p["field"] == "incident_date" for p in bad["problems"])
