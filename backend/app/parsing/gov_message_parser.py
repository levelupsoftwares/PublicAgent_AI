"""Government-message parser (spec §14).

Usable as an agent tool AND as a plain function. Takes pasted free text and:
- classifies whether it looks like a government communication,
- extracts a reference number (regex for CMP-YYYY-NNNNNN, LLM fallback for looser
  formats),
- extracts likely status / required action (via the LLM abstraction),
- returns a plain-language explanation + suggested next action.

Pasted text is NEVER treated as verified fact on its own — callers persist it in
gov_message_logs and label derived UI elements as user-pasted/unverified.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

REFERENCE_RE = re.compile(r"\b(CMP-\d{4}-\d{6})\b")
LOOSE_REF_RE = re.compile(r"\b([A-Z]{2,5}-\d{4}-\d{4,8})\b")

GOV_SIGNALS = [
    r"\bcomplaint\b", r"\breference\b", r"\bref\s*(no|number|#)", r"\bcase\b",
    r"\bhelpline\b", r"\bauthority\b", r"\bdepartment\b", r"\bstatus\b",
    r"\bdocs?uments?\b", r"\bwithin \d+ (days|hours)\b", r"\bpid\b", r"\bgov(?:t|ernment)\b",
    r"\bpolice\b", r"\bmunicipal\b", r"\bwapda\b", r"\bsui\b", r"\bndeep\b", r"\bgarrison\b",
]
STATUS_KEYWORD_MAP = [
    (r"resolv(e|ed)|closed.*(favor|favour)", "resolved"),
    (r"additional (documents?|information|doc)|require[sd]? (more|additional)|provide the following|bring the following",
     "additional_info_required"),
    (r"under (review|process)|being reviewed", "under_review"),
    (r"investigat(e|ing|ion|ed)", "investigating"),
    (r"has been received|registered|received your complaint|acknowledg", "received"),
]
CHANNEL_HINTS = [
    (r"\bsms\b|\btext message\b", "sms"),
    (r"\bemail\b|\binbox\b|\bdear (citizen|sir|madam)\b", "email"),
]


@dataclass
class GovMessageAnalysis:
    looks_government: bool
    confidence: float
    reference_number: str | None = None
    status: str | None = None
    required_action: str | None = None
    channel: str = "unknown"
    explanation: str = ""
    next_action: str | None = None
    extracted: dict = field(default_factory=dict)


def _llm():
    from app.llm.client import get_llm_client

    return get_llm_client()


def extract_reference(text: str) -> str | None:
    m = REFERENCE_RE.search(text)
    if m:
        return m.group(1)
    m = LOOSE_REF_RE.search(text)
    return m.group(1) if m else None


def looks_like_government_message(text: str) -> tuple[bool, float]:
    low = text.lower()
    hits = sum(1 for p in GOV_SIGNALS if re.search(p, low))
    has_ref = bool(REFERENCE_RE.search(text) or LOOSE_REF_RE.search(text))
    score = hits * 0.15 + (0.4 if has_ref else 0.0)
    score = min(score, 0.98)
    return score >= 0.4, round(score, 2)


def guess_status(text: str) -> str | None:
    low = text.lower()
    for pattern, status in STATUS_KEYWORD_MAP:
        if re.search(pattern, low):
            return status
    return None


def guess_channel(text: str) -> str:
    for pattern, channel in CHANNEL_HINTS:
        if re.search(pattern, text.lower()):
            return channel
    return "unknown"


def _plain_explanation(status: str | None, ref: str | None, action: str | None) -> str:
    parts = []
    if ref:
        parts.append(f"Your message refers to complaint {ref}.")
    else:
        parts.append("The message you pasted mentions a complaint, but I couldn't find a "
                     "reference number in it.")
    if status == "additional_info_required":
        parts.append("It says the authority needs more documents or information from you "
                     "before the complaint can move forward.")
    elif status == "resolved":
        parts.append("It appears the authority has resolved the complaint.")
    elif status == "under_review":
        parts.append("It says the complaint is currently being reviewed.")
    elif status == "investigating":
        parts.append("It says the complaint is in the investigation stage.")
    elif status == "received":
        parts.append("It confirms the authority has received/registered the complaint.")
    else:
        parts.append("I couldn't confidently determine the status it describes.")
    if action:
        parts.append(f"Suggested next step: {action}")
    return " ".join(parts)


def _next_action(status: str | None) -> str | None:
    if status == "additional_info_required":
        return ("Attach the requested documents to your complaint (you can upload them in "
                "the chat) and reply to the authority.")
    if status == "resolved":
        return "Review the resolution in your complaint timeline. You can close it or ask about an appeal."
    if status in ("received", "under_review"):
        return "No action needed right now — keep your reference number for future checks."
    if status == "investigating":
        return "The authority is investigating; preserve any new evidence you have."
    return None


def parse_government_message(text: str, *, use_llm: bool = True) -> GovMessageAnalysis:
    """Plain-function entry point (also used as an agent tool)."""
    looks, confidence = looks_like_government_message(text)
    ref = extract_reference(text)
    status = guess_status(text)
    channel = guess_channel(text)
    action = _next_action(status)

    if use_llm and (not status or not ref):
        try:
            resp = _llm().generate(
                [{"role": "user", "content": text[:2000]}],
                system="[TASK: analyze_gov_message] Extract reference number, status and "
                       "required action from the pasted government message. Return JSON with "
                       "keys reference_number, status, required_action, channel, confidence.",
                json_mode=True,
            )
            data = resp.json()
            if isinstance(data, dict):
                ref = ref or data.get("reference_number") or None
                status = status or data.get("status") or None
                action = action or data.get("required_action") or None
                if data.get("channel") and channel == "unknown":
                    channel = data["channel"]
                try:
                    confidence = max(confidence, float(data.get("confidence") or 0))
                except (TypeError, ValueError):
                    pass
        except Exception:
            pass  # LLM unavailable — regex results still stand

    explanation = _plain_explanation(status, ref, action)
    return GovMessageAnalysis(
        looks_government=looks,
        confidence=confidence,
        reference_number=ref,
        status=status,
        required_action=action,
        channel=channel,
        explanation=explanation,
        next_action=action,
        extracted={"raw_length": len(text)},
    )
