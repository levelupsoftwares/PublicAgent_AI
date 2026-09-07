"""Submission nodes: prepare_complaint, request_confirmation, submit_complaint,
store_complaint, schedule_followup.

Submission is HARD-GATED on user_confirmation=True and idempotent per draft
(idempotency_key generated once, persisted in state; repeated submits return the
same reference instead of creating duplicate cases)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.agent.events import (
    AWAITING_CONFIRMATION,
    COMPLAINT_PREPARED,
    COMPLAINT_SUBMITTED,
    FOLLOWUP_SCHEDULED,
    REFERENCE_RECEIVED,
)
from app.agent.nodes.base import Services, emit, say
from app.agent.state import AgentState
from app.config import settings

STATUS_DISPLAY = {
    "draft": "Draft", "submitted": "Submitted", "received": "Received",
    "under_review": "Under Review", "additional_info_required": "Additional Info Required",
    "investigating": "Investigating", "resolved": "Resolved", "closed": "Closed",
}

FIELD_LABELS = {}  # filled from requirements at prepare time


def _label_for(state: AgentState, field: str) -> str:
    for f in state.get("required_information") or []:
        if f["field"] == field:
            return f["label"]
    return field.replace("_", " ").title()


def _display_value(value):
    if value == "__SKIPPED__":
        return "— skipped by you —"
    if value in (None, ""):
        return "—"
    return str(value)


def make_prepare_complaint(services: Services):
    def prepare_complaint(state: AgentState) -> dict:
        collected = dict(state.get("collected_information") or {})
        auth = (state.get("government_data") or {}).get("authority", {}) or {}
        unverified = [
            _label_for(state, k) for k, v in collected.items()
            if v not in (None, "") and k not in ("description",)
        ]
        evidence = state.get("evidence") or []
        complaint = {
            "idempotency_key": (state.get("complaint") or {}).get("idempotency_key")
                               or str(uuid.uuid4()),
            "category": state.get("issue_type") or "general_grievance",
            "department": auth.get("name", ""),
            "jurisdiction": auth.get("jurisdiction", ""),
            "description": collected.get("description", ""),
            "structured_fields": collected,
            "unverified_fields": unverified,
        }
        card = {
            "type": "review",
            "title": "Review your complaint before submission",
            "complaint": {
                "category": complaint["category"],
                "department": complaint["department"] or "Demo authority",
                "jurisdiction": complaint["jurisdiction"],
                "description": complaint["description"],
            },
            "fields": [
                {"field": k, "label": _label_for(state, k), "value": _display_value(v),
                 "skipped": v == "__SKIPPED__"}
                for k, v in collected.items() if k != "description"
            ],
            "unverified_fields": unverified,
            "evidence": [
                {"filename": e.get("filename"), "summary": e.get("extracted_summary"),
                 "unverified": True}
                for e in evidence
            ],
            "labels": {
                "unverified": "You reported — not independently verified",
                "mock": "Authority details are demo / mock government data",
            },
            "warning": "Nothing is submitted until you press Confirm & Submit.",
        }
        out = say(state,
                  "Here is the complete draft. Please check every line — especially the "
                  "items marked as unverified — before you confirm.",
                  card)
        out.update(emit(state, COMPLAINT_PREPARED, {
            "category": complaint["category"], "fields": sorted(collected.keys()),
        }))
        out.update({"complaint": complaint, "phase": "awaiting_confirmation"})
        return out

    return prepare_complaint


def make_request_confirmation(services: Services):
    def request_confirmation(state: AgentState) -> dict:
        if state.get("user_confirmation"):
            # Arrived via the Confirm action — proceed straight to submission.
            return {"phase": "awaiting_confirmation"}
        card = {
            "type": "confirmation",
            "title": "Confirm & Submit",
            "body": "Do you confirm that this draft is accurate and that you want to submit "
                    "it to the (demo) authority? Nothing has been sent yet.",
            "confirm_label": "Confirm & Submit",
            "cancel_label": "Go Back",
        }
        out = say(state, "Please confirm to submit — or go back to make changes.", card)
        out.update(emit(state, AWAITING_CONFIRMATION, {}))
        out["phase"] = "awaiting_confirmation"
        return out

    return request_confirmation


def make_submit_complaint(services: Services):
    def submit_complaint(state: AgentState) -> dict:
        if not state.get("user_confirmation"):
            out = say(state, "Submission cancelled — nothing was filed. You can review and "
                             "confirm again whenever you're ready.", {
                "type": "notice", "level": "info",
                "title": "Not submitted", "body": "No complaint was sent. Your draft is saved.",
            })
            out["phase"] = "awaiting_confirmation"
            return out

        # Idempotency: already submitted in a previous invocation?
        if state.get("reference_number"):
            return {}  # edge continues; store_complaint will no-op

        complaint = state.get("complaint") or {}
        try:
            result = services.gov.submit_complaint(complaint)
        except Exception as exc:  # demo resilience
            out = say(state, "The (demo) submission service returned an error. Please try "
                             "Confirm & Submit again — it will not create a duplicate.",
                      {"type": "notice", "level": "error", "title": "Submission failed",
                       "body": str(exc)[:200]})
            out["errors"] = [f"submit_complaint: {exc}"]
            return out

        ref = result.get("reference_number")
        out = {
            "reference_number": ref,
            "complaint_status": result.get("status", "submitted"),
        }
        out.update(emit(state, COMPLAINT_SUBMITTED, {
            "reference_number": ref, "submitted_at": result.get("submitted_at"),
            "source": result.get("source", "mock"),
        }))
        out.update(emit(state, REFERENCE_RECEIVED, {"reference_number": ref}))
        return out

    return submit_complaint


def make_store_complaint(services: Services):
    def store_complaint(state: AgentState) -> dict:
        ref = state.get("reference_number")
        if not ref:
            return {}
        db = services.db
        from app.models import Complaint, Conversation, Evidence

        conv = db.get(Conversation, state.get("conversation_id"))
        existing_id = conv.complaint_id if conv else None
        complaint_row = db.get(Complaint, existing_id) if existing_id else None

        complaint = state.get("complaint") or {}
        if complaint_row is None:
            complaint_row = Complaint(
                reference_number=ref,
                user_id=state.get("user_id"),
                conversation_id=state.get("conversation_id"),
                category=complaint.get("category", "general_grievance"),
                department=complaint.get("department", ""),
                jurisdiction=complaint.get("jurisdiction"),
                status="submitted",
                description=complaint.get("description", ""),
                structured_fields=complaint.get("structured_fields", {}),
                unverified_fields=complaint.get("unverified_fields", []),
                submitted_at=datetime.now(timezone.utc),
            )
            db.add(complaint_row)
            db.flush()
            if conv:
                conv.complaint_id = complaint_row.id
        else:
            # Idempotent re-run: refresh but never duplicate.
            complaint_row.status = "submitted"
            complaint_row.submitted_at = complaint_row.submitted_at or datetime.now(timezone.utc)

        # Attach any draft evidence uploaded during this conversation.
        if state.get("conversation_id"):
            drafts = db.execute(
                select(Evidence).where(Evidence.conversation_id == state["conversation_id"],
                                       Evidence.complaint_id.is_(None))
            ).scalars().all()
            for ev in drafts:
                ev.complaint_id = complaint_row.id
        db.commit()

        from app.models import ComplaintEvent

        already = db.execute(
            select(ComplaintEvent).where(
                ComplaintEvent.complaint_id == complaint_row.id,
                ComplaintEvent.event_type == "SUBMITTED",
            )
        ).scalars().first()
        if not already:
            db.add(ComplaintEvent(
                complaint_id=complaint_row.id, event_type="SUBMITTED",
                old_status=None, new_status="submitted",
                metadata_={"source": "agent", "reference_number": ref},
            ))
            db.commit()

        return {"complaint_id": complaint_row.id}
    return store_complaint


def make_schedule_followup(services: Services):
    def schedule_followup(state: AgentState) -> dict:
        complaint_id = state.get("complaint_id")
        if not complaint_id:
            return {}
        db = services.db
        from app.models import Complaint, ComplaintEvent, FollowupJob

        interval = max(int(settings.FOLLOWUP_CHECK_INTERVAL_SECONDS), 5)
        scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=interval)
        job = FollowupJob(complaint_id=complaint_id, scheduled_for=scheduled_for, status="pending")
        db.add(job)
        row = db.get(Complaint, complaint_id)
        if row:
            row.next_check_at = scheduled_for
        db.commit()

        card = {
            "type": "status",
            "title": "Complaint submitted",
            "reference_number": state.get("reference_number"),
            "status": "submitted",
            "status_display": STATUS_DISPLAY.get("submitted"),
            "department": (state.get("complaint") or {}).get("department"),
            "tracking": {
                "active": True,
                "next_check_at": scheduled_for.isoformat(),
                "interval_seconds": interval,
            },
            "note": "Demo / mock government data. I'll watch the status and notify you here "
                    "when it changes.",
        }
        out = say(state,
                  f"Done — your complaint was submitted to the (demo) authority and received "
                  f"reference {state.get('reference_number')}. I've scheduled follow-up "
                  f"checks every {interval} seconds; you'll get a notification here when the "
                  f"status changes.",
                  card)
        out.update(emit(state, FOLLOWUP_SCHEDULED, {
            "complaint_id": complaint_id, "scheduled_for": scheduled_for.isoformat(),
        }))
        schedule = {"next_check_at": scheduled_for.isoformat(), "interval_seconds": interval}
        return {"follow_up_schedule": schedule, "phase": "tracking",
                "workflow_events": out.get("workflow_events", []),
                "assistant_messages": out.get("assistant_messages", [])}

    return schedule_followup
