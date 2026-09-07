"""SQLAlchemy models — translation of the spec's §11 schema.

Small documented deviations (see DECISIONS.md):
- conversations.agent_state (JSONB): persists the LangGraph AgentState between chat turns.
- notifications: in-app notification inbox required by the spec's behaviour ("notifying
  the citizen in-app") but absent from the §11 table list.
- evidence.conversation_id: allows uploads while a complaint is still a draft.
- kb_chunks.embedding: Vector(EMBEDDING_DIM) on PostgreSQL/pgvector; JSON on SQLite.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db import Base, is_postgres


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _embedding_type():
    """pgvector Vector on PostgreSQL, JSON fallback on SQLite."""
    if is_postgres():
        try:
            from pgvector.sqlalchemy import Vector

            from app.config import settings

            return Vector(settings.EMBEDDING_DIM)
        except Exception:  # pragma: no cover - pgvector not installed
            return JSON
    return JSON


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(Text, nullable=False)
    email = Column(Text, unique=True, nullable=False, index=True)
    phone = Column(Text, nullable=True)
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    complaints = relationship("Complaint", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    complaint_id = Column(String(36), ForeignKey("complaints.id"), nullable=True)
    title = Column(Text, nullable=True)
    agent_state = Column(JSON, nullable=False, default=dict)  # persisted AgentState
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user | assistant | system
    content = Column(Text, nullable=False)
    structured_payload = Column(JSON, nullable=True)  # typed card for the frontend
    workflow_events = Column(JSON, nullable=True)     # events produced during this turn
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")


class Complaint(Base):
    __tablename__ = "complaints"

    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_RECEIVED = "received"
    STATUS_UNDER_REVIEW = "under_review"
    STATUS_ADDITIONAL_INFO = "additional_info_required"
    STATUS_INVESTIGATING = "investigating"
    STATUS_RESOLVED = "resolved"
    STATUS_CLOSED = "closed"

    id = Column(String(36), primary_key=True, default=_uuid)
    reference_number = Column(String(40), unique=True, nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=True, index=True)
    category = Column(String(60), nullable=False)       # issue_type e.g. police_misconduct
    department = Column(String(200), nullable=False)    # authority display name
    jurisdiction = Column(String(200), nullable=True)
    status = Column(String(40), nullable=False, default=STATUS_DRAFT, index=True)
    description = Column(Text, nullable=False)
    structured_fields = Column(JSON, nullable=False, default=dict)   # collected_information
    unverified_fields = Column(JSON, nullable=False, default=list)   # [field names]
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    next_check_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="complaints")
    events = relationship(
        "ComplaintEvent", back_populates="complaint", cascade="all, delete-orphan",
        order_by="ComplaintEvent.created_at",
    )
    evidence = relationship("Evidence", back_populates="complaint")
    followup_jobs = relationship("FollowupJob", back_populates="complaint")


class ComplaintEvent(Base):
    __tablename__ = "complaint_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # e.g. STATUS_UPDATED, SUBMITTED
    old_status = Column(String(40), nullable=True)
    new_status = Column(String(40), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    complaint = relationship("Complaint", back_populates="events")


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(String(36), primary_key=True, default=_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id"), nullable=True, index=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=True, index=True)
    filename = Column(Text, nullable=False)
    content_type = Column(String(120), nullable=False)
    storage_key = Column(Text, nullable=False)
    extracted_summary = Column(Text, nullable=True)  # AI-extracted — always labeled unverified
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    complaint = relationship("Complaint", back_populates="evidence")


class FollowupJob(Base):
    __tablename__ = "followup_jobs"

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"

    id = Column(String(36), primary_key=True, default=_uuid)
    complaint_id = Column(String(36), ForeignKey("complaints.id"), nullable=False, index=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=False, index=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default=STATUS_PENDING, index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    complaint = relationship("Complaint", back_populates="followup_jobs")


class GovMessageLog(Base):
    __tablename__ = "gov_message_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    complaint_id = Column(String(36), ForeignKey("complaints.id"), nullable=True, index=True)
    raw_text = Column(Text, nullable=False)
    channel = Column(String(40), nullable=True)  # sms | email | unknown
    extracted_reference = Column(String(40), nullable=True)
    extracted_status = Column(String(40), nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)


class KBDocument(Base):
    __tablename__ = "kb_documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    title = Column(Text, nullable=False)
    source_type = Column(String(40), nullable=False, default="demo_kb")
    source_ref = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    chunks = relationship("KBChunk", back_populates="document", cascade="all, delete-orphan")


class KBChunk(Base):
    __tablename__ = "kb_chunks"

    id = Column(String(36), primary_key=True, default=_uuid)
    document_id = Column(String(36), ForeignKey("kb_documents.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(_embedding_type(), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    document = relationship("KBDocument", back_populates="chunks")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    complaint_id = Column(String(36), ForeignKey("complaints.id"), nullable=True, index=True)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
