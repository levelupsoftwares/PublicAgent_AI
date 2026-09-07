"""Government-message graph nodes:
analyze_user_message → detect_government_message → extract_reference →
retrieve_complaint → analyze_status → update_complaint → explain_to_user → END

Everything derived from a pasted message is labelled user-pasted / unverified
unless the (mock) status API corroborates it."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.agent.events import REQUEST_RECEIVED, STATUS_UPDATED
from app.agent.nodes.base import Services, emit, say
from app.agent.state import AgentState
from app.parsing import gov_message_parser as parser

STATUS_DISPLAY = {
    "draft": "Draft", "submitted": "Submitted", "received": "Received",
    "under_review": "Under Review", "additional_info_required": "Additional Info Required",
    "investigating": "Investigating", "resolved": "Resolved", "closed": "Closed",
}


def make_analyze_user_message(services: Services):
    def analyze_user_message(state: AgentState) -> dict:
        text = state.get("user_request") or ""
        out = {"government_message": text}
        out.update(emit(state, REQUEST_RECEIVED, {"channel": "pasted_message",
                                                  "length": len(text)}))
        return out
    return analyze_user_message


def make_detect_government_message(services: Services):
    def detect_government_message(state: AgentState) -> dict:
        text = state.get("government_message") or ""
        looks, confidence = parser.looks_like_government_message(text)
        return {"extracted_message_data": {"looks_government": looks,
                                           "confidence": confidence}}
    return detect_government_message


def make_extract_reference(services: Services):
    def extract_reference(state: AgentState) -> dict:
        text = state.get("government_message") or ""
        ref = parser.extract_reference(text)
        data = dict(state.get("extracted_message_data") or {})
        data["reference_number"] = ref
        return {"extracted_message_data": data}
    return extract_reference


def make_retrieve_complaint(services: Services):
    def retrieve_complaint(state: AgentState) -> dict:
        data = dict(state.get("extracted_message_data") or {})
        ref = data.get("reference_number")
        complaint_id = None
        found = False
        if ref:
            from app.models import Complaint

            row = services.db.execute(
                select(Complaint).where(Complaint.reference_number == ref,
                                        Complaint.user_id == state.get("user_id"))
            ).scalars().first()
            if row:
                found = True
                complaint_id = row.id
                data["complaint_id"] = row.id
                data["known_status"] = row.status
        data["complaint_found"] = found
        return {"extracted_message_data": data, "complaint_id": complaint_id}
    return retrieve_complaint


def make_analyze_status(services: Services):
    def analyze_status(state: AgentState) -> dict:
        text = state.get("government_message") or ""
        analysis = parser.parse_government_message(text, use_llm=True)
        data = dict(state.get("extracted_message_data") or {})
        data.update({
            "status": analysis.status,
            "required_action": analysis.required_action,
            "channel": analysis.channel,
            "confidence": analysis.confidence,
            "looks_government": analysis.looks_government,
        })
        return {"extracted_message_data": data}
    return analyze_status


def make_update_complaint(services: Services):
    def update_complaint(state: AgentState) -> dict:
        data = dict(state.get("extracted_message_data") or {})
        complaint_id = data.get("complaint_id")
        updates: dict = {}

        # Always persist the pasted message log.
        from app.models import GovMessageLog

        services.db.add(GovMessageLog(
            user_id=state.get("user_id"),
            complaint_id=complaint_id,
            raw_text=(state.get("government_message") or "")[:4000],
            channel=data.get("channel"),
            extracted_reference=data.get("reference_number"),
            extracted_status=data.get("status"),
            confidence=data.get("confidence"),
        ))
        services.db.commit()

        if not complaint_id or not data.get("status"):
            return updates

        from app.models import Complaint, ComplaintEvent, Notification

        row = services.db.get(Complaint, complaint_id)
        if not row:
            return updates

        # Corroboration: does the (mock) status API agree right now?
        verified = False
        mock_status = None
        try:
            gov_status = services.gov.get_complaint_status(row.reference_number)
            if gov_status.get("found"):
                mock_status = gov_status.get("status")
                verified = mock_status == data.get("status")
        except Exception:
            pass

        old = row.status
        row.status = data["status"]
        row.updated_at = datetime.now(timezone.utc)
        services.db.add(ComplaintEvent(
            complaint_id=row.id, event_type="STATUS_UPDATED",
            old_status=old, new_status=data["status"],
            metadata_={
                "source": "user_pasted",
                "verified": verified,
                "mock_status": mock_status,
                "channel": data.get("channel"),
                "confidence": data.get("confidence"),
                "label": "From a message you pasted — not independently verified"
                         + unless_verified(verified),
            },
        ))
        services.db.add(Notification(
            user_id=state.get("user_id"), complaint_id=row.id,
            title=f"Complaint {row.reference_number} — status updated (from your pasted message)",
            body=f"Status set to {STATUS_DISPLAY.get(data['status'], data['status'])}. "
                 + ("Corroborated by the (mock) status API."
                    if verified else "Not independently verified yet."),
        ))
        services.db.commit()

        data["verified"] = verified
        data["previous_status"] = old
        updates["extracted_message_data"] = data
        updates.update(emit(state, STATUS_UPDATED, {
            "complaint_id": row.id, "reference_number": row.reference_number,
            "old_status": old, "new_status": data["status"],
            "source": "user_pasted", "verified": verified,
        }))
        return updates

    return update_complaint


def unless_verified(verified: bool) -> str:
    return "" if verified else " (unverified)"


def make_explain_to_user(services: Services):
    def explain_to_user(state: AgentState) -> dict:
        data = dict(state.get("extracted_message_data") or {})
        looks = data.get("looks_government")
        ref = data.get("reference_number")
        status = data.get("status")
        verified = data.get("verified", False)

        if not looks:
            prose = ("This doesn't look like a government message to me — I don't see the "
                     "usual markers (reference number, department wording, status language). "
                     "If you believe it is official, paste the full text again or tell me the "
                     "reference number directly.")
            card = {
                "type": "gov_message_analysis",
                "looks_government": False,
                "confidence": data.get("confidence", 0),
                "reference_number": ref,
                "extracted_status": status,
                "status_display": STATUS_DISPLAY.get(status) if status else None,
                "required_action": None,
                "verification": "unverified",
            }
            out = say(state, prose, card)
            return out

        if not ref:
            prose = ("This looks like an official message, but I couldn't find a reference "
                     "number in it. If you have a complaint reference (like CMP-2026-001928), "
                     "paste it and I'll reconcile it against your complaints.")
            card = {
                "type": "gov_message_analysis",
                "looks_government": True,
                "confidence": data.get("confidence"),
                "reference_number": None,
                "extracted_status": status,
                "status_display": STATUS_DISPLAY.get(status) if status else None,
                "required_action": data.get("required_action"),
                "verification": "unverified",
            }
            out = say(state, prose, card)
            return out

        if not data.get("complaint_found"):
            prose = (f"I found reference {ref} in your message, but it doesn't match any "
                     f"complaint stored under your account. Double-check the number — or file "
                     f"a complaint first, then paste the message again.")
            card = {
                "type": "gov_message_analysis",
                "looks_government": True,
                "confidence": data.get("confidence"),
                "reference_number": ref,
                "extracted_status": status,
                "status_display": STATUS_DISPLAY.get(status) if status else None,
                "required_action": data.get("required_action"),
                "verification": "not_found",
                "found": False,
            }
            out = say(state, prose, card)
            return out

        verified_label = ("Corroborated by the (mock) status API" if verified
                          else "From a message you pasted — not independently verified")
        prose = (f"I read the message you pasted: it refers to complaint {ref}"
                 + (f" and indicates the status is {STATUS_DISPLAY.get(status, status)}"
                    if status else "")
                 + f". {data.get('required_action') or 'No immediate action seems required.'} "
                 f"Remember: this came from your pasted text — I treated it as "
                 + ("confirmed (the demo status API agrees)" if verified
                    else "unverified until the demo status API corroborates it") + ".")

        card = {
            "type": "gov_message_analysis",
            "looks_government": True,
            "confidence": data.get("confidence"),
            "reference_number": ref,
            "extracted_status": status,
            "status_display": STATUS_DISPLAY.get(status) if status else None,
            "required_action": data.get("required_action"),
            "channel": data.get("channel"),
            "verification": "verified" if verified else "user_pasted_unverified",
            "verification_label": verified_label,
            "found": True,
            "previous_status": data.get("previous_status"),
        }
        out = say(state, prose, card)
        return out

    return explain_to_user
