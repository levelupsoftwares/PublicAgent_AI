"""AgentState — the shared object that flows through the LangGraph graphs.

Implemented exactly as spec §6 (TypedDict, total=False), extended minimally with
documented fields (see DECISIONS.md): phase tracking, draft metadata for
idempotency, emergency flag, and pending assistant messages / events produced by
nodes during one invocation.
"""
from __future__ import annotations

from typing import Annotated, TypedDict


def merge_list(left: list | None, right: list | None) -> list:
    """Append-only merge used for events / messages / errors accumulation."""
    out = list(left or [])
    for item in right or []:
        out.append(item)
    return out


class AgentState(TypedDict, total=False):
    # --- identity / request ---
    conversation_id: str
    user_id: str
    user_request: str
    intent: str                          # understand_options | report | file_complaint | not_sure | unknown
    phase: str                           # new | options_presented | collecting | awaiting_confirmation | tracking

    # --- turn orchestration (set by the chat orchestrator / nodes) ---
    guidance_requested: bool             # route this turn through present_guidance
    guidance_mode: str | None            # understand | not_sure
    asked_fields: list[str]              # fields asked so far (accumulates; prevents re-asking)
    awaiting_fields: list[str]           # fields asked in the LAST question (awaiting answers)
    initial_request: str | None          # citizen's very first message (description prefill)
    complaint_id: str | None             # set by store_complaint

    # --- classification / routing ---
    issue_type: str
    department: str
    jurisdiction: str
    service: str
    emergency: bool

    # --- knowledge + mock gov data ---
    official_context: list[dict]         # retrieved RAG chunks + source metadata
    government_data: dict                # result of the mock gov lookup

    # --- progressive information collection ---
    required_information: list[dict]     # [{field,label,required,status}]
    collected_information: dict
    evidence: list[dict]                 # file refs + AI-extracted (unverified) summaries

    # --- complaint assembly / submission ---
    complaint: dict                      # assembled payload pre-submission
    complaint_status: str
    reference_number: str | None
    user_confirmation: bool
    follow_up_schedule: dict | None

    # --- government message path ---
    government_message: str | None
    extracted_message_data: dict | None

    # --- bookkeeping ---
    errors: Annotated[list[str], merge_list]
    workflow_events: Annotated[list[dict], merge_list]
    assistant_messages: Annotated[list[dict], merge_list]  # {content, structured_payload}
