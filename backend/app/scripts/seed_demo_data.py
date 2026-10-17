"""Seed idempotent demo data for PublicAgent AI.

This module was previously EMPTY, which crashed backend startup with
`ImportError: cannot import name 'seed_if_empty'` (main.py imports it when
SEED_ON_START is enabled) — the seed now restores the documented behaviour:

    python -m app.scripts.seed_demo_data     # manual run
    SEED_ON_START=1 (default in .env.example) → auto-run at boot

What gets seeded (only if the demo citizen has NO complaints/conversations yet):
  - the demo citizen user (citizen@demo.pk / demo1234 — same as demo-login)
  - the knowledge base (app.rag.ingest.ingest_kb — markdown docs + embeddings)
  - 3 demo complaints across the mock-government lifecycle
    (received / under_review / resolved), registered in the mock gov case
    store via MockGovernmentClient.seed_case so status tracking works
  - matching complaint events, in-app notifications and one pending follow-up
    job so the scheduler has something to process
  - 2 demo conversations with realistic transcripts

Everything is clearly demo/mock data. Re-running never duplicates anything.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

logger = logging.getLogger("publicagent.seed")

# Reference numbers must match the pattern the parser recognises:
# [A-Z]{2,5}-<year>-<4..8 digits>  (see app.gov + message parser).
_REFS = ("CMP-2026-001928", "CMP-2026-001931", "CMP-2026-001934")


def seed_if_empty(db: Session | None = None) -> bool:
    """Seed demo data once. Returns True when something was created."""
    owned = False
    if db is None:
        from app.db import SessionLocal

        db = SessionLocal()
        owned = True
    try:
        # Standalone runs (CLI) still need tables; harmless when they exist.
        from app.db import Base, engine

        import app.models  # noqa: F401

        Base.metadata.create_all(bind=engine)

        from app.api.auth import ensure_demo_user
        from app.models import (Complaint, Conversation, FollowupJob, Message,
                                Notification)
        from app.rag.ingest import ingest_kb

        user = ensure_demo_user(db)

        has_complaints = db.execute(
            select(func.count()).select_from(Complaint)
            .where(Complaint.user_id == user.id)
        ).scalar() or 0
        has_conversations = db.execute(
            select(func.count()).select_from(Conversation)
            .where(Conversation.user_id == user.id)
        ).scalar() or 0
        if has_complaints or has_conversations:
            return False  # already seeded — stay idempotent

        # 1) Knowledge base (idempotent: keyed by source_ref)
        kb_stats = ingest_kb(db)

        now = datetime.now(timezone.utc)
        complaints: list[Complaint] = []

        # 2) Complaint #1 — police misconduct, under review (active case)
        c1 = Complaint(
            reference_number=_REFS[0], user_id=user.id,
            category="police_misconduct",
            department="Provincial Police Complaints Authority (Demo Data)",
            jurisdiction="Punjab (Demo)",
            status="under_review",
            description=(
                "On 12 June 2026 at Bagh-e-Jinnah, Lahore, a traffic warden "
                "demanded an on-the-spot payment after stopping me for a "
                "routine document check. I refused and was threatened with "
                "detention. I can identify the officer by his belt number."),
            structured_fields={
                "incident_date": "2026-06-12",
                "incident_time": "17:30",
                "location": "Bagh-e-Jinnah, Lahore",
                "police_station": "Model Town Police Station",
                "officer_badge_number": "__SKIPPED__",
                "description": "Officer demanded on-the-spot payment and threatened detention.",
            },
            unverified_fields=["officer_badge_number", "police_station"],
            submitted_at=now - timedelta(hours=26),
        )
        # 3) Complaint #2 — utility service, resolved (finished lifecycle)
        c2 = Complaint(
            reference_number=_REFS[1], user_id=user.id,
            category="utility_service",
            department="Electric Supply Company Consumer Complaints Cell (Demo Data)",
            jurisdiction="Regional (Demo)",
            status="resolved",
            description=(
                "Persistent power outages of 6-8 hours daily in my area for "
                "two weeks while the monthly bill shows estimated readings "
                "instead of actual meter readings. Consumer account 4455-8812."),
            structured_fields={
                "account_number": "4455-8812",
                "location": "Gulberg III, Lahore",
                "incident_date": "2026-06-02",
                "description": "Prolonged load-shedding plus estimated billing despite a working meter.",
            },
            unverified_fields=[],
            submitted_at=now - timedelta(days=9),
            last_checked_at=now - timedelta(minutes=10),
            next_check_at=now + timedelta(minutes=10),
        )
        # 4) Complaint #3 — police misconduct, just received (fresh case)
        c3 = Complaint(
            reference_number=_REFS[2], user_id=user.id,
            category="police_misconduct",
            department="Citizen Police Liaison Cell (Demo Data)",
            jurisdiction="Karachi Division (Demo)",
            status="received",
            description=(
                "The desk officer at my local police station refused to "
                "register my FIR about a stolen motorcycle and told me to "
                "\"settle it outside\". This happened yesterday evening."),
            structured_fields={
                "incident_date": (now - timedelta(days=1)).date().isoformat(),
                "incident_time": "20:15",
                "location": "Saddar, Karachi",
                "police_station": "Saddar Police Station",
                "description": "FIR refused for a stolen motorcycle; advised to settle privately.",
            },
            unverified_fields=["police_station"],
            submitted_at=now - timedelta(minutes=45),
        )
        complaints = [c1, c2, c3]
        for c in complaints:
            db.add(c)
        db.flush()

        # 5) Complaint events (mirrors the lifecycle the agent produces)
        from app.models import ComplaintEvent

        def _event(complaint: Complaint, etype: str, old: str | None,
                   new: str | None, meta: dict, at: datetime) -> ComplaintEvent:
            return ComplaintEvent(complaint_id=complaint.id, event_type=etype,
                                  old_status=old, new_status=new, metadata_=meta,
                                  created_at=at)

        db.add(_event(c1, "SUBMITTED", None, "submitted",
                      {"note": "Complaint submitted after explicit citizen confirmation"},
                      c1.submitted_at))
        db.add(_event(c1, "STATUS_UPDATED", "submitted", "received",
                      {"source": "mock"}, c1.submitted_at + timedelta(minutes=1)))
        db.add(_event(c1, "STATUS_UPDATED", "received", "under_review",
                      {"source": "mock"}, c1.submitted_at + timedelta(minutes=3)))

        db.add(_event(c2, "SUBMITTED", None, "submitted",
                      {"note": "Complaint submitted after explicit citizen confirmation"},
                      c2.submitted_at))
        db.add(_event(c2, "STATUS_UPDATED", "submitted", "resolved",
                      {"source": "mock",
                       "note": "Utility replaced the faulty transformer; billing corrected"},
                      c2.submitted_at + timedelta(days=2)))

        db.add(_event(c3, "SUBMITTED", None, "submitted",
                      {"note": "Complaint submitted after explicit citizen confirmation"},
                      c3.submitted_at))
        db.add(_event(c3, "STATUS_UPDATED", "submitted", "received",
                      {"source": "mock"}, c3.submitted_at + timedelta(minutes=1)))

        # 6) Notifications (in-app inbox)
        db.add_all([
            Notification(
                user_id=user.id, complaint_id=c1.id,
                title="Your complaint is under review",
                body=f"Complaint {c1.reference_number} has been assigned to an "
                     "inquiry officer at the Provincial Police Complaints Authority "
                     "(demo data). You will be notified when the status changes.",
                read=False, created_at=now - timedelta(hours=25)),
            Notification(
                user_id=user.id, complaint_id=c2.id,
                title="Complaint resolved",
                body=f"Complaint {c2.reference_number} was marked resolved by the "
                     "utility's complaints cell (demo data). The transformer was "
                     "replaced and your billing was corrected. You may close or "
                     "appeal it from the complaint page.",
                read=True, created_at=now - timedelta(days=7)),
            Notification(
                user_id=user.id, complaint_id=c3.id,
                title="Complaint received",
                body=f"Complaint {c3.reference_number} was acknowledged by the "
                     "Citizen Police Liaison Cell (demo data). Keep your "
                     "reference number for all follow-ups.",
                read=False, created_at=now - timedelta(minutes=44)),
        ])

        # 7) One pending follow-up job so the scheduler has work on boot
        db.add(FollowupJob(
            complaint_id=c3.id, scheduled_for=now + timedelta(minutes=2),
            status="pending"))

        # 8) Demo conversations with realistic transcripts
        conv1 = Conversation(
            user_id=user.id, complaint_id=c1.id,
            title="Traffic warden demanded on-the-spot payment…",
            agent_state={"phase": "tracking", "issue_type": "police_misconduct",
                         "initial_request": (c1.description or "")[:800]},
            created_at=now - timedelta(hours=27),
        )
        db.add(conv1)
        db.flush()
        db.add_all([
            Message(conversation_id=conv1.id, role="user",
                    content="A traffic warden stopped me near Bagh-e-Jinnah and demanded "
                            "money on the spot. When I refused he threatened to detain me. "
                            "This is not right, what can I do?",
                    created_at=now - timedelta(hours=27)),
            Message(conversation_id=conv1.id, role="assistant",
                    content="I'm sorry that happened — being pressured for money during a "
                            "routine check is a serious matter. I'm not deciding anything, "
                            "but based on the (demo) guidance I retrieved, this sounds like "
                            "it may be police misconduct, typically handled by a complaints "
                            "authority. You can file a formal complaint with a reference "
                            "number you can track, or simply report the incident on record.",
                    structured_payload={"type": "options",
                                        "options": ["file", "report", "understand", "not_sure"]},
                    created_at=now - timedelta(hours=26, minutes=58)),
            Message(conversation_id=conv1.id, role="user", content="File a Formal Complaint",
                    created_at=now - timedelta(hours=26, minutes=57)),
            Message(conversation_id=conv1.id, role="assistant",
                    content="Your complaint has been submitted with reference CMP-2026-001928 "
                            "(demo data). I'll keep watching its status and will notify you "
                            "here the moment anything changes.",
                    structured_payload={"type": "complaint_submitted",
                                        "reference_number": _REFS[0]},
                    created_at=now - timedelta(hours=26)),
        ])

        conv2 = Conversation(
            user_id=user.id, complaint_id=None,
            title="Electricity outages and estimated billing",
            agent_state={"phase": "options_presented",
                         "issue_type": "utility_service",
                         "initial_request": (c2.description or "")[:800]},
            created_at=now - timedelta(days=10),
        )
        db.add(conv2)
        db.flush()
        db.add_all([
            Message(conversation_id=conv2.id, role="user",
                    content="We have 6 to 8 hours of load shedding every day and my bill "
                            "shows estimated readings even though my meter works fine. "
                            "Who do I even complain to about this?",
                    created_at=now - timedelta(days=10)),
            Message(conversation_id=conv2.id, role="assistant",
                    content="That combination — prolonged outages plus estimated billing "
                            "despite a working meter — is a known category of utility "
                            "service complaints (demo guidance). It is normally handled "
                            "first by the utility's own consumer complaints cell, and "
                            "having your consumer/account number ready speeds things up. "
                            "Would you like to file a formal complaint or just report it?",
                    structured_payload={"type": "options",
                                        "options": ["file", "report", "understand", "not_sure"]},
                    created_at=now - timedelta(days=9, minutes=23, hours=23)),
        ])

        # 9) Register the three cases in the mock government case store so
        #    status polling / tracking works for seeded complaints too.
        _register_mock_cases(complaints)

        db.commit()
        logger.info(
            "Demo data seeded: %s complaints, 2 conversations, KB %s",
            len(complaints), kb_stats)
        return True
    finally:
        if owned:
            db.close()


def _register_mock_cases(complaints) -> None:
    """Pre-register seeded complaints in the mock gov case store."""
    from datetime import datetime as _dt

    from app.gov.mock_client import MockGovernmentClient

    gov = MockGovernmentClient()
    for c in complaints:
        try:
            submitted = c.submitted_at
            if isinstance(submitted, _dt) and submitted.tzinfo is None:
                submitted = submitted.replace(tzinfo=timezone.utc)
            gov.seed_case(
                c.reference_number,
                submitted_at=submitted or _dt.now(timezone.utc),
                category=c.category,
                department=c.department,
                jurisdiction=c.jurisdiction,
                description=c.description,
                structured_fields=c.structured_fields or {},
                status_override=c.status,
                idempotency_key=f"seed-{c.reference_number}",
            )
        except Exception:  # pragma: no cover - store write issues must not abort seeding
            logger.exception("Could not pre-register %s in the mock gov store",
                             c.reference_number)


def main() -> None:
    import sys

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    created = seed_if_empty()
    print("Demo data seeded (fresh)." if created
          else "Demo data already present — nothing to do (idempotent).")
    sys.exit(0 if created else 0)


if __name__ == "__main__":
    main()
