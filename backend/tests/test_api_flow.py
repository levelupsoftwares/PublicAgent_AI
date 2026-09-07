"""Full API integration test: demo login → chat journey → submit → force-advance
→ notification → paste-message flow (the spec §16/§19 core scenario)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(seeded):
    from app.main import app

    # Never start the real scheduler inside tests.
    with TestClient(app) as c:
        yield c


def _auth(client) -> dict:
    tok = client.post("/api/auth/demo-login").json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _turn(client, headers, conv, content=None, action=None):
    body = {"conversation_id": conv, "content": content or ""}
    if action:
        body["action"] = action
    r = client.post("/api/chat", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_full_demo_journey(client, seeded):
    headers = _auth(client)

    # Health reports mock provider + sqlite
    health = client.get("/api/health").json()
    assert health["llm_provider"] == "mock"

    # 1-2: describe → neutral options, NOT an immediate filing
    r = _turn(client, headers, None, "A police officer misbehaved with me.")
    conv = r["conversation_id"]
    cards = [m["structured_payload"]["type"] for m in r["messages"] if m["structured_payload"]]
    assert "options" in cards
    assert "review" not in cards
    evs = [e["event_type"] for e in r["workflow_events"]]
    assert evs[:2] == ["REQUEST_RECEIVED", "INTENT_IDENTIFIED"]

    # 3: Understand My Options → RAG-grounded guidance + citations
    r = _turn(client, headers, conv, action={"type": "option", "option": "understand"})
    cards = [m["structured_payload"]["type"] for m in r["messages"] if m["structured_payload"]]
    assert "guidance" in cards and "source_citations" in cards

    # 4: file → progressive collection
    r = _turn(client, headers, conv, action={"type": "option", "option": "file"})
    card = next(m["structured_payload"] for m in r["messages"]
                if m["structured_payload"] and m["structured_payload"]["type"] == "information_request")
    assert len(card["questions"]) <= 2

    # 5-7: answer everything (single field per turn keeps extraction deterministic)
    answers = ["My name is Ahmed Raza", "It happened 2026-03-02 around 6 pm",
               "Near Mall Road, Lahore", "Mall Road police station",
               "The officer stopped me and demanded money", "My phone is 0300-1234567"]
    review_seen = False
    for a in answers:
        r = _turn(client, headers, conv, a)
        types = [m["structured_payload"]["type"] for m in r["messages"] if m["structured_payload"]]
        review_seen = review_seen or "review" in types
        if review_seen:
            break

    assert review_seen, "review card must appear once required info is collected"

    # 8-10: explicit confirmation gate → submit → reference
    r = _turn(client, headers, conv, action={"type": "confirm", "value": True})
    ref_card = next(m["structured_payload"] for m in r["messages"]
                    if m["structured_payload"] and m["structured_payload"]["type"] == "status")
    ref = ref_card["reference_number"]
    assert ref and ref.startswith("CMP-")

    # Idempotency: re-confirm creates no duplicate
    r2 = _turn(client, headers, conv, action={"type": "confirm", "value": True})
    assert not any(m["structured_payload"] and m["structured_payload"]["type"] == "status"
                   for m in r2["messages"])

    # 11: complaint persisted, follow-up job exists
    complaints = client.get("/api/complaints", headers=headers).json()
    mine = next(c for c in complaints if c["reference_number"] == ref)
    assert mine["status"] == "submitted"
    detail = client.get(f"/api/complaints/{mine['id']}", headers=headers).json()
    assert any(e["event_type"] == "SUBMITTED" for e in detail["events"])

    # 12: demo force-advance → scheduler propagates → notification
    adv = client.post("/api/demo/advance-status", json={"complaint_id": mine["id"]},
                      headers=headers).json()
    assert adv["force_advance"]["found"] is True
    assert adv["scheduler_run"]["changed"] >= 1
    notes = client.get("/api/notifications", headers=headers).json()
    assert any(ref in n["title"] for n in notes)

    # 13: paste a government SMS → analysed, timeline updated, labeled unverified
    sms = (f"Police Complaints Authority: Complaint {ref} requires additional "
           "documents. Submit your CNIC copy within 3 days.")
    r = _turn(client, headers, conv, sms)
    card = next(m["structured_payload"] for m in r["messages"]
                if m["structured_payload"] and m["structured_payload"]["type"] == "gov_message_analysis")
    assert card["reference_number"] == ref
    assert card["extracted_status"] == "additional_info_required"
    assert card["verification"] in ("user_pasted_unverified", "verified")
    detail = client.get(f"/api/complaints/{mine['id']}", headers=headers).json()
    pasted_events = [e for e in detail["events"] if e["metadata"].get("source") == "user_pasted"]
    assert pasted_events, "pasted-message event must be on the timeline"

    # Workflow events endpoint powers the panel
    ev = client.get(f"/api/conversations/{conv}/events", headers=headers).json()
    types = [e["event_type"] for e in ev["events"]]
    assert "FOLLOWUP_SCHEDULED" in types and "STATUS_UPDATED" in types


def test_emergency_flag_surfaces_helpline(client, seeded):
    headers = _auth(client)
    r = _turn(client, headers, None,
              "A police officer threatened to kill me and is beating me right now")
    emergency = [m for m in r["messages"]
                 if m["structured_payload"] and m["structured_payload"]["type"] == "emergency"]
    assert emergency
    assert emergency[0]["structured_payload"]["helpline"]["number"] == "15"


def test_upload_validation(client, seeded, tmp_path):
    headers = _auth(client)
    # Rejected type
    r = client.post("/api/evidence", headers=headers,
                    files={"file": ("evil.exe", b"MZ...", "application/x-msdownload")})
    assert r.status_code == 415
    # Accepted PDF
    r = client.post("/api/evidence", headers=headers,
                    files={"file": ("report.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert r.status_code == 200
    assert "unverified" in r.json()["label"].lower()
