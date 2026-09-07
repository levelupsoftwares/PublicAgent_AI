"""All API routers in one module map: auth, chat, conversations, complaints,
evidence, gov-message, demo, notifications."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import (
    Complaint,
    ComplaintEvent,
    Conversation,
    Evidence,
    GovMessageLog,
    Message,
    Notification,
    User,
)
from app.parsing import gov_message_parser as parser
from app.schemas import (
    ChatResponse,
    ComplaintDetailOut,
    ComplaintOut,
    MessageOut,
    NotificationOut,
)
from app.storage.client import get_storage_client
from app.storage.local import build_object_key

api_router = APIRouter()

ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".pdf"}


# ----------------------------------------------------------------- chat
@api_router.post("/api/chat", response_model=ChatResponse, tags=["chat"])
def chat_endpoint(
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.api.chat import run_chat_turn
    from app.schemas import ChatRequest

    try:
        body = ChatRequest(**payload)
    except Exception as e:
        raise HTTPException(422, f"Invalid request: {e}")
    try:
        conv_id, messages, events, phase = run_chat_turn(
            db, user, body.conversation_id, body.content,
            body.action.model_dump() if body.action else None,
        )
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return ChatResponse(
        conversation_id=conv_id,
        messages=[MessageOut(**_message_out(m)) for m in messages],
        workflow_events=events,
        agent_phase=phase,
    )


def _message_out(m: Message) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content or "",
        "structured_payload": m.structured_payload,
        "workflow_events": m.workflow_events,
        "created_at": m.created_at.isoformat() if m.created_at else datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------------- conversations
@api_router.get("/api/conversations", tags=["chat"])
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Conversation).where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc()).limit(50)
    ).scalars().all()
    return [
        {"id": c.id, "title": c.title, "complaint_id": c.complaint_id,
         "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat()}
        for c in rows
    ]


@api_router.get("/api/conversations/{conversation_id}/messages", tags=["chat"])
def conversation_messages(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    rows = db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    ).scalars().all()
    return [_message_out(m) for m in rows]


@api_router.get("/api/conversations/{conversation_id}/events", tags=["chat"])
def conversation_events(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Polling endpoint for the workflow panel (spec §8: polling is fine for MVP)."""
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    rows = db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    ).scalars().all()
    events = []
    for m in rows:
        for ev in (m.workflow_events or []):
            events.append(ev)
    return {"conversation_id": conversation_id, "events": events,
            "agent_state": conv.agent_state or {}}


# ----------------------------------------------------------- complaints
@api_router.get("/api/complaints", response_model=list[ComplaintOut], tags=["complaints"])
def list_complaints(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Complaint).where(Complaint.user_id == user.id)
        .order_by(Complaint.updated_at.desc())
    ).scalars().all()
    return [_complaint_out(c) for c in rows]


@api_router.get("/api/complaints/{complaint_id}", response_model=ComplaintDetailOut,
                tags=["complaints"])
def complaint_detail(
    complaint_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.get(Complaint, complaint_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, "Complaint not found")
    events = db.execute(
        select(ComplaintEvent).where(ComplaintEvent.complaint_id == c.id)
        .order_by(ComplaintEvent.created_at.asc())
    ).scalars().all()
    evidence = db.execute(
        select(Evidence).where(Evidence.complaint_id == c.id)
        .order_by(Evidence.created_at.asc())
    ).scalars().all()
    out = _complaint_out(c)
    out["events"] = [{
        "id": ev.id, "event_type": ev.event_type, "old_status": ev.old_status,
        "new_status": ev.new_status, "metadata": ev.metadata_ or {},
        "created_at": ev.created_at.isoformat(),
    } for ev in events]
    out["evidence"] = [{
        "id": e.id, "filename": e.filename, "content_type": e.content_type,
        "extracted_summary": e.extracted_summary, "created_at": e.created_at.isoformat(),
    } for e in evidence]
    return out


def _complaint_out(c: Complaint) -> dict:
    return {
        "id": c.id, "reference_number": c.reference_number, "category": c.category,
        "department": c.department, "jurisdiction": c.jurisdiction, "status": c.status,
        "description": c.description, "structured_fields": c.structured_fields or {},
        "unverified_fields": c.unverified_fields or [],
        "submitted_at": c.submitted_at.isoformat() if c.submitted_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "next_check_at": c.next_check_at.isoformat() if c.next_check_at else None,
    }


# -------------------------------------------------------------- evidence
@api_router.post("/api/evidence", tags=["evidence"])
async def upload_evidence(
    file: UploadFile = File(...),
    conversation_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.config import settings
    from app.llm.client import get_llm_client

    ext = ("." + file.filename.rsplit(".", 1)[-1].lower()) if "." in (file.filename or "") else ""
    if file.content_type not in ALLOWED_TYPES and ext not in ALLOWED_EXT:
        raise HTTPException(415, "Only JPG, PNG and PDF files are allowed.")
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(413, f"File too large — limit is {settings.MAX_UPLOAD_MB} MB.")

    key = build_object_key(user.id, file.filename or "upload.bin")
    import io

    storage = get_storage_client()
    storage.save(key, io.BytesIO(data), file.content_type or "application/octet-stream")

    # AI extraction via the LLM abstraction — always labelled unverified.
    summary = None
    try:
        resp = get_llm_client().generate(
            [{"role": "user", "content": f"Filename: {file.filename}\nContent-Type: {file.content_type}\nSize: {len(data)} bytes"}],
            system="[TASK: summarize_evidence] Summarize the uploaded attachment for a "
                   "complaint record. Return JSON {summary, extracted_fields, unverified}. "
                   "Never invent details not present in the attachment.",
            json_mode=True,
        )
        d = resp.json() or {}
        summary = d.get("summary")
        if d.get("unverified", True):
            summary = (summary or "") + " [AI-extracted — unverified]"
    except Exception:
        summary = None

    ev = Evidence(
        complaint_id=None,
        conversation_id=conversation_id,
        filename=file.filename or "upload.bin",
        content_type=file.content_type or "application/octet-stream",
        storage_key=key,
        extracted_summary=summary,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return {
        "id": ev.id, "filename": ev.filename, "content_type": ev.content_type,
        "extracted_summary": ev.extracted_summary, "created_at": ev.created_at.isoformat(),
        "label": "AI-extracted — unverified" if summary else "Stored — not yet analyzed",
    }


@api_router.get("/api/evidence/{evidence_id}/file", tags=["evidence"])
def evidence_file(
    evidence_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ev = db.get(Evidence, evidence_id)
    if ev is None:
        raise HTTPException(404, "Not found")
    if ev.conversation_id:
        conv = db.get(Conversation, ev.conversation_id)
        if conv is None or conv.user_id != user.id:
            raise HTTPException(403, "Forbidden")
    elif ev.complaint_id:
        c = db.get(Complaint, ev.complaint_id)
        if c is None or c.user_id != user.id:
            raise HTTPException(403, "Forbidden")
    storage = get_storage_client()
    try:
        data = storage.open(ev.storage_key)
    except Exception:
        raise HTTPException(404, "File missing from storage")
    from fastapi import Response

    return Response(content=data, media_type=ev.content_type or "application/octet-stream",
                    headers={"Content-Disposition": f'inline; filename="{ev.filename}"'})


# ----------------------------------------------------------- gov-message
@api_router.post("/api/gov-message/analyze", tags=["gov-message"])
def analyze_gov_message(
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Plain-function entry point for the parser (also usable as an agent tool)."""
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "text is required")
    analysis = parser.parse_government_message(text, use_llm=True)
    ref = analysis.reference_number
    complaint_id = None
    if ref:
        row = db.execute(
            select(Complaint).where(Complaint.reference_number == ref,
                                    Complaint.user_id == user.id)
        ).scalars().first()
        complaint_id = row.id if row else None
    db.add(GovMessageLog(
        user_id=user.id, complaint_id=complaint_id, raw_text=text[:4000],
        channel=analysis.channel, extracted_reference=ref,
        extracted_status=analysis.status, confidence=analysis.confidence,
    ))
    db.commit()
    return {
        "looks_government": analysis.looks_government,
        "confidence": analysis.confidence,
        "reference_number": ref,
        "status": analysis.status,
        "required_action": analysis.required_action,
        "channel": analysis.channel,
        "explanation": analysis.explanation,
        "next_action": analysis.next_action,
        "complaint_found": bool(complaint_id),
        "verification_label": "From a message you pasted — not independently verified",
    }


# ----------------------------------------------------------- notifications
@api_router.get("/api/notifications", response_model=list[NotificationOut], tags=["notifications"])
def list_notifications(
    since: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(Notification).where(Notification.user_id == user.id).order_by(
        Notification.created_at.desc()).limit(50)
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            q = q.where(Notification.created_at > since_dt)
        except ValueError:
            pass
    rows = db.execute(q).scalars().all()
    return [{
        "id": n.id, "complaint_id": n.complaint_id, "title": n.title, "body": n.body,
        "read": n.read, "created_at": n.created_at.isoformat(),
    } for n in rows]


@api_router.post("/api/notifications/mark-read", tags=["notifications"])
def mark_notifications_read(payload: dict, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    ids = payload.get("ids") or []
    if ids:
        rows = db.execute(
            select(Notification).where(Notification.user_id == user.id,
                                       Notification.id.in_(ids))
        ).scalars().all()
        for n in rows:
            n.read = True
        db.commit()
    return {"marked": len(ids)}


# ----------------------------------------------------------------- demo
@api_router.post("/api/demo/advance-status", tags=["demo"])
def demo_advance_status(payload: dict, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Demo-only safety net: force-advance a complaint's (mock) status, then run
    one scheduler pass so the change propagates immediately for a live demo."""
    from app.gov.client import get_gov_client
    from app.scheduler.followup_jobs import run_followup_check
    from app.db import SessionLocal

    complaint_id = payload.get("complaint_id")
    reference = payload.get("reference_number")
    if not complaint_id and not reference:
        raise HTTPException(422, "complaint_id or reference_number required")
    if complaint_id:
        row = db.get(Complaint, complaint_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(404, "Complaint not found")
        reference = row.reference_number
    else:
        row = db.execute(
            select(Complaint).where(Complaint.reference_number == reference,
                                    Complaint.user_id == user.id)
        ).scalars().first()
        if row is None:
            raise HTTPException(404, "Complaint not found")
        reference = row.reference_number
    if not reference:
        raise HTTPException(422, "This complaint has no reference number yet (not submitted).")
    result = get_gov_client().force_advance(reference)
    if not result.get("found"):
        raise HTTPException(404, result.get("error", "not found in mock registry"))
    # Make this complaint's follow-up job immediately due so the change propagates
    # in this demo pass (the scheduler itself stays on its normal interval).
    from app.models import FollowupJob

    now = datetime.now(timezone.utc)
    jobs = db.execute(
        select(FollowupJob).where(FollowupJob.complaint_id == row.id,
                                  FollowupJob.status == FollowupJob.STATUS_PENDING)
    ).scalars().all()
    for j in jobs:
        j.scheduled_for = now
        j.next_retry_at = None
    db.commit()
    scheduler_result = run_followup_check(SessionLocal)
    return {"force_advance": result, "scheduler_run": scheduler_result,
            "note": "Demo / mock government data."}


@api_router.get("/api/demo/mock-state", tags=["demo"])
def demo_mock_state(user: User = Depends(get_current_user)):
    from app.gov.client import get_gov_client

    gov = get_gov_client()
    store = gov._load()
    cases = []
    for ref, case in store.get("cases", {}).items():
        cases.append({
            "reference_number": ref,
            "status": gov._computed_status(case),
            "submitted_at": case.get("submitted_at"),
            "override": case.get("explicit_status_override"),
        })
    return {"source": "mock", "cases": cases,
            "note": "Demo / mock government data — internal registry inspection."}
