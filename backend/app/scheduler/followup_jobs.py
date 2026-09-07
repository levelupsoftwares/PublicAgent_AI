"""APScheduler-based follow-up engine (spec §13).

- Runs INSIDE the FastAPI process on the configured interval (env-controlled).
- Selects followup_jobs rows where scheduled_for <= now() and status = pending,
  calls GovernmentServiceClient.get_complaint_status(), compares with the stored
  status, and on change: writes complaint_events (STATUS_UPDATED), updates the
  complaint, creates an in-app notification, reschedules the next check.
- Basic retry handling (retry_count++, backoff on next_retry_at); one bad job must
  never crash the loop. Complaints already resolved/closed are never polled.
- Job state lives in Postgres/SQLite (survives restarts) — swap for Celery+Redis
  only if this outgrows a single process (documented in DECISIONS.md).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select, update

from app.config import settings

logger = logging.getLogger("publicagent.scheduler")

_scheduler: BackgroundScheduler | None = None

RETRY_BACKOFF_SECONDS = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_followup_check(db_session_factory) -> dict:
    """One scheduler pass. Also callable from the demo force-advance endpoint."""
    from app.gov.client import get_gov_client
    from app.models import Complaint, ComplaintEvent, FollowupJob, Notification

    checked, changed, failed = 0, 0, 0
    gov = get_gov_client()
    db = db_session_factory()
    try:
        now = _now()
        due = db.execute(
            select(FollowupJob).where(
                FollowupJob.status == FollowupJob.STATUS_PENDING,
                FollowupJob.scheduled_for <= now,
            )
        ).scalars().all()
        # Basic retry due-ness
        due = [j for j in due if j.next_retry_at is None or j.next_retry_at <= now]

        for job in due:
            try:
                complaint = db.get(Complaint, job.complaint_id)
                if complaint is None:
                    job.status = FollowupJob.STATUS_DONE
                    db.commit()
                    continue
                if complaint.status in (Complaint.STATUS_RESOLVED, Complaint.STATUS_CLOSED):
                    job.status = FollowupJob.STATUS_DONE
                    db.commit()
                    continue

                result = gov.get_complaint_status(complaint.reference_number)
                checked += 1
                complaint.last_checked_at = now
                job.last_run_at = now

                if result.get("found"):
                    new_status = result.get("status")
                    if new_status and new_status != complaint.status:
                        old = complaint.status
                        complaint.status = new_status
                        db.add(ComplaintEvent(
                            complaint_id=complaint.id, event_type="STATUS_UPDATED",
                            old_status=old, new_status=new_status,
                            metadata_={"source": "scheduler", "reference_number":
                                       complaint.reference_number},
                        ))
                        db.add(Notification(
                            user_id=complaint.user_id, complaint_id=complaint.id,
                            title=f"Complaint {complaint.reference_number} — status updated",
                            body=f"Status changed from {old.replace('_', ' ')} to "
                                 f"{new_status.replace('_', ' ')} (demo data).",
                        ))
                        changed += 1
                    # Reschedule the next check.
                    job.scheduled_for = now + timedelta(
                        seconds=settings.FOLLOWUP_CHECK_INTERVAL_SECONDS)
                    job.retry_count = 0
                    job.next_retry_at = None
                    complaint.next_check_at = job.scheduled_for
                    job.status = FollowupJob.STATUS_PENDING
                else:
                    # Unknown reference in the mock registry — retry with backoff.
                    job.retry_count = (job.retry_count or 0) + 1
                    job.next_retry_at = now + timedelta(seconds=RETRY_BACKOFF_SECONDS * job.retry_count)
                db.commit()
            except Exception as exc:  # never crash the loop on one bad job
                logger.warning("followup job %s failed: %s", job.id, exc)
                failed += 1
                try:
                    job.retry_count = (job.retry_count or 0) + 1
                    job.next_retry_at = _now() + timedelta(
                        seconds=RETRY_BACKOFF_SECONDS * min(job.retry_count, 10))
                    job.status = (FollowupJob.STATUS_FAILED
                                  if job.retry_count >= 5 else FollowupJob.STATUS_PENDING)
                    db.commit()
                except Exception:
                    db.rollback()
        return {"checked": checked, "changed": changed, "failed": failed, "due": len(due)}
    finally:
        db.close()


def start_scheduler(db_session_factory) -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    interval = max(int(settings.FOLLOWUP_CHECK_INTERVAL_SECONDS), 5)
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        run_followup_check,
        trigger="interval",
        seconds=interval,
        args=[db_session_factory],
        id="publicagent_followup_check",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )
    _scheduler.start()
    logger.info("Follow-up scheduler started (interval=%ss)", interval)
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
