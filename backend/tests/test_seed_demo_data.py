"""Tests for app.scripts.seed_demo_data — the previously-empty seed module."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import (Complaint, ComplaintEvent, Conversation, FollowupJob,
                        KBChunk, Message, Notification)


def test_seed_creates_demo_dataset(db, user):
    from app.scripts.seed_demo_data import seed_if_empty

    assert seed_if_empty(db) is True

    n_complaints = db.execute(
        select(func.count()).select_from(Complaint)
        .where(Complaint.user_id == user.id)).scalar()
    assert n_complaints == 3

    statuses = {c.status for c in db.execute(select(Complaint)).scalars()}
    assert {"received", "under_review", "resolved"} <= statuses

    refs = {c.reference_number for c in db.execute(select(Complaint)).scalars()}
    assert all(r.startswith("CMP-2026-") for r in refs)

    n_msgs = db.execute(select(func.count()).select_from(Message)).scalar()
    assert n_msgs >= 6
    n_conv = db.execute(select(func.count()).select_from(Conversation)).scalar()
    assert n_conv == 2
    n_events = db.execute(select(func.count()).select_from(ComplaintEvent)).scalar()
    assert n_events >= 5
    n_notifs = db.execute(select(func.count()).select_from(Notification)).scalar()
    assert n_notifs >= 3
    n_jobs = db.execute(select(func.count()).select_from(FollowupJob)).scalar()
    assert n_jobs >= 1

    # Knowledge base ingested with embeddings (mock provider, EMBEDDING_DIM wide)
    n_chunks = db.execute(select(func.count()).select_from(KBChunk)).scalar()
    assert n_chunks > 0


def test_seed_is_idempotent(db, user):
    from app.scripts.seed_demo_data import seed_if_empty

    assert seed_if_empty(db) is True
    assert seed_if_empty(db) is False  # second run: nothing duplicated

    n_complaints = db.execute(select(func.count()).select_from(Complaint)).scalar()
    assert n_complaints == 3
    n_conv = db.execute(select(func.count()).select_from(Conversation)).scalar()
    assert n_conv == 2


def test_seeded_cases_registered_in_mock_gov_store(db, user):
    from app.gov.mock_client import MockGovernmentClient
    from app.scripts.seed_demo_data import seed_if_empty

    seed_if_empty(db)
    gov = MockGovernmentClient()
    for c in db.execute(select(Complaint)).scalars():
        status = gov.get_complaint_status(c.reference_number)
        assert status.get("source") == "mock"
        assert status.get("status") == c.status
