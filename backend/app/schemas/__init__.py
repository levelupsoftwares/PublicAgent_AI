"""Pydantic request/response schemas."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: Optional[str] = None
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class ChatAction(BaseModel):
    type: str = Field(description="option | skip | confirm | cancel")
    option: Optional[str] = None
    field: Optional[str] = None
    value: Optional[bool] = None


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    content: str = Field(default="", max_length=6000)
    action: Optional[ChatAction] = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    structured_payload: Optional[dict] = None
    workflow_events: Optional[list] = None
    created_at: str


class ConversationOut(BaseModel):
    id: str
    title: Optional[str] = None
    complaint_id: Optional[str] = None
    created_at: str
    updated_at: str


class ChatResponse(BaseModel):
    conversation_id: str
    messages: list[MessageOut]
    workflow_events: list[dict]
    agent_phase: str
    # Which engine produced this reply ("groq", "model_studio", "mock", ...).
    # Lets the UI (and debugging) show whether a real LLM or the offline demo
    # engine answered — silent mock fallbacks were previously undetectable.
    llm_provider: str = ""


class ComplaintOut(BaseModel):
    id: str
    reference_number: Optional[str] = None
    category: str
    department: str
    jurisdiction: Optional[str] = None
    status: str
    description: str
    structured_fields: dict
    unverified_fields: list
    submitted_at: Optional[str] = None
    updated_at: str
    next_check_at: Optional[str] = None


class ComplaintEventOut(BaseModel):
    id: str
    event_type: str
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    created_at: str


class ComplaintDetailOut(ComplaintOut):
    events: list[ComplaintEventOut]
    evidence: list[dict]


class NotificationOut(BaseModel):
    id: str
    complaint_id: Optional[str] = None
    title: str
    body: str
    read: bool
    created_at: str


class DemoAdvanceRequest(BaseModel):
    complaint_id: Optional[str] = None
    reference_number: Optional[str] = None


class EvidenceOut(BaseModel):
    id: str
    filename: str
    content_type: str
    extracted_summary: Optional[str] = None
    created_at: str
