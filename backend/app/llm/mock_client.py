"""Deterministic offline LLM engine ("mock provider").

Purpose: keep the entire demo and test-suite runnable with ZERO external API keys
(sandbox, CI, judge-laptop fallback). It is rule-based and clearly labelled as a
mock everywhere in the UI. Real deployments set LLM_PROVIDER=model_studio and this
class is never used. See DECISIONS.md.

Contract parity with the real adapters:
  generate(messages, system=..., json_mode=...) -> LLMResponse
  embed(texts) -> list[list[float]]  (deterministic feature-hashing embedding)

Agent nodes tag their system prompts with "[TASK: <name>]" so the mock engine can
produce the exact structured output each task expects. Real LLMs simply read the
marker as part of the instruction text — harmless and mildly helpful.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime
from typing import Iterable

from app.config import settings
from app.llm.client import LLMResponse

DANGER_PATTERNS = [
    r"\bkill(ed|ing)?\b", r"\bthreat(en|ened|ening)?\b", r"\bbeat(en|ing)?\b",
    r"\btortur(e|ed|ing)\b", r"\bweapon\b", r"\bgun\b", r"\bshoot(ing)?\b",
    r"\bhurt(ed|ing)?\b", r"\bin danger\b", r"\bafraid for my life\b", r"\bfear for my life\b",
    r"\babduct(ed|ion)?\b", r"\bkidnap(ped|ing)?\b", r"\bviolence\b", r"\brape\b",
]

POLICE_KEYWORDS = [
    "police", "officer", "misbehav", "misconduct", " constable", "shaheed", "thana",
    "station house officer", "sho", "bribe", "custody", "fir", "detector", "beat constable",
    "sub-inspector", "asi", "inhuman", "illegal detention", "extortion",
]
UTILITY_KEYWORDS = [
    "electricity", "electric", "power outage", "load shedding", "meter", "bill",
    "transformer", "water supply", "sewerage", "gas pressure", "sanitation", "garbage",
]


def _text_of(messages: Iterable[dict]) -> str:
    parts = []
    for m in messages:
        c = m.get("content", "")
        parts.append(c if isinstance(c, str) else str(c))
    return "\n".join(parts)


def _has_danger(text: str) -> bool:
    low = text.lower()
    return any(re.search(p, low) for p in DANGER_PATTERNS)


class MockLLMClient:
    provider_name = "mock"

    # ------------------------------------------------------------------ LLM API
    def generate(self, messages: Iterable[dict], *, system: str | None = None,
                 json_mode: bool = False) -> LLMResponse:
        sys_text = system or ""
        user_text = _text_of(messages)
        task = ""
        m = re.search(r"\[TASK:\s*([a-z_]+)\]", sys_text)
        if m:
            task = m.group(1)

        handler = getattr(self, f"_task_{task}", None)
        if handler is not None:
            return LLMResponse(content=handler(user_text, sys_text), usage={"provider": "mock"})

        # Generic conversational fallback.
        return LLMResponse(
            content=self._generic_reply(user_text), usage={"provider": "mock"}
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

    # ------------------------------------------------------------- embeddings
    def _hash_embed(self, text: str) -> list[float]:
        """Deterministic bag-of-token feature hashing, L2-normalised.

        Meaningful enough at demo scale for cosine-similarity RAG without any
        external embedding API. Dimension follows EMBEDDING_DIM (default 1536).
        """
        dim = settings.EMBEDDING_DIM
        vec = [0.0] * dim
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if (h >> 128) % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [round(v / norm, 6) for v in vec]

    # ----------------------------------------------------------------- tasks
    def _task_classify_issue(self, user_text: str, sys_text: str) -> str:
        low = user_text.lower()
        police = sum(1 for k in POLICE_KEYWORDS if k in low)
        utility = sum(1 for k in UTILITY_KEYWORDS if k in low)
        if police >= utility and police > 0:
            issue = "police_misconduct"
        elif utility > 0:
            issue = "utility_service"
        else:
            issue = "general_grievance"
        return json_dumps({
            "issue_type": issue,
            "confidence": 0.82 if issue != "general_grievance" else 0.55,
            "summary": first_sentence(user_text),
            "emergency": _has_danger(user_text),
        })

    def _task_extract_fields(self, user_text: str, sys_text: str) -> str:
        """Extract values for the pending fields listed in the system prompt.

        The system prompt (built by the collect_information node) contains a
        'PENDING FIELDS:' block like '- incident_date (required)'. The mock
        extractor uses patterns per field name; unknown free text is assigned to
        the first pending field.
        """
        fields = re.findall(r"-\s*([a-z_]+)\s*\((\w+)\)", sys_text)
        pending = [name for name, _req in fields]
        result: dict[str, str] = {}
        text = user_text.strip()
        low = text.lower()
        if not pending:
            return json_dumps({"fields": {}, "notes": "no pending fields"})

        NEGATIONS = ("skip", "n/a", "na", "none", "unknown", "not sure", "no idea",
                     "don't know", "dont know", "do not know", "i don't know",
                     "i dont know", "i do not know", "no ")
        if any(low.startswith(n) for n in NEGATIONS):
            # Prefer the field whose keywords appear in the sentence; otherwise the
            # single pending field; otherwise the first one (documented heuristic).
            HINTS = {
                "officer_badge_number": ("badge", "belt"),
                "officer_name": ("officer", "constable", "inspector"),
                "complainant_phone": ("phone", "contact", "mobile"),
                "incident_time": ("time", "clock", "hour"),
                "incident_date": ("date", "when"),
                "location": ("location", "place", "where", "area"),
                "police_station": ("station", "thana"),
                "account_number": ("account", "consumer"),
            }
            targets = [name for name in pending
                       if any(h in low for h in HINTS.get(name, ()))]
            if not targets and len(pending) == 1:
                targets = [pending[0]]
            if not targets:
                targets = [pending[0]]
            return json_dumps({"fields": {t: "__SKIPPED__" for t in targets},
                               "notes": "citizen skipped the field"})

        for name in pending:
            if name in ("incident_date", "date_of_incident"):
                m = re.search(
                    r"(\d{4}-\d{2}-\d{2})|(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})|"
                    r"(yesterday|last night|today|this morning|last week)", text, re.IGNORECASE)
                if m:
                    result[name] = normalise_date(m.group(0).lower())
                    break
            if name in ("incident_time", "time_of_incident"):
                m = re.search(r"\b(\d{1,2}[:.]\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm))\b", text, re.IGNORECASE)
                if m:
                    result[name] = m.group(1)
                    continue
            if name == "location":
                m = re.search(r"\b(?:near|at|in front of|opposite|in)\s+([A-Za-z0-9 .,'-]{3,60})", text, re.IGNORECASE)
                if m:
                    result[name] = m.group(1).strip(" .,")
                    break
            if name in ("police_station", "station"):
                m = re.search(r"\b([A-Za-z0-9 .'()-]{2,50}?)\s*(?:police station|thana)\b", text, re.IGNORECASE)
                if m:
                    result[name] = f"{m.group(1).strip().title()} Police Station"
                    continue
            if name in ("officer_name", "officer_badge_number"):
                m = re.search(r"\b(?:officer|constable|inspector|si|asi|sho)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", text, re.IGNORECASE)
                if m:
                    result[name] = m.group(1).title()
                    continue
            if name == "complainant_name":
                m = re.search(r"\b(?:my name is|i am|i'm)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", text, re.IGNORECASE)
                if m:
                    result[name] = m.group(1).title()
                    continue
            if name == "complainant_phone":
                m = re.search(r"\b(0?3\d{2}[- ]?\d{7}|\+92\d{10})\b", text)
                if m:
                    result[name] = m.group(1)
                    continue
            if name == "description":
                result[name] = first_sentence(text) or text[:300]
                continue

        return json_dumps({"fields": result, "notes": "mock heuristic extraction"})

    def _task_analyze_gov_message(self, user_text: str, sys_text: str) -> str:
        low = user_text.lower()
        status_map = [
            (r"resolv(e|ed)|closed.*(favor|favour)|complaint has been resolved", "resolved"),
            (r"additional (documents?|information)|require[sd]? (more|additional)|provide the following", "additional_info_required"),
            (r"under (review|process)|being reviewed", "under_review"),
            (r"investigat(e|ing|ion|ed)", "investigating"),
            (r"has been received|registered|received your complaint", "received"),
        ]
        status = None
        for pattern, st in status_map:
            if re.search(pattern, low):
                status = st
                break
        ref = None
        m = re.search(r"\b([A-Z]{2,5}-\d{4}-\d{4,8})\b", user_text)
        if m:
            ref = m.group(1)
        action = None
        if status == "additional_info_required":
            action = "Attach the requested documents to your complaint and reply to the authority."
        elif status == "resolved":
            action = "Review the resolution in your complaint timeline; you may close or appeal it."
        elif status in ("received", "under_review"):
            action = "No action needed right now — keep your reference number for future checks."
        elif status == "investigating":
            action = "The authority is investigating; preserve any new evidence you have."
        return json_dumps({
            "reference_number": ref,
            "status": status,
            "required_action": action,
            "channel": "sms" if len(user_text) < 400 else "email",
            "confidence": 0.75 if status else 0.4,
        })

    def _task_summarize_evidence(self, user_text: str, sys_text: str) -> str:
        return json_dumps({
            "summary": "Attachment logged for review. Automated content extraction is "
                       "unavailable in offline demo mode, so no details were inferred.",
            "extracted_fields": [],
            "unverified": True,
        })

    def _task_extract_reference(self, user_text: str, sys_text: str) -> str:
        m = re.search(r"\b([A-Z]{2,5}-\d{4}-\d{4,8})\b", user_text)
        return json_dumps({"reference_number": m.group(1) if m else None})

    # ---------------------------------------------------------------- generic
    def _generic_reply(self, user_text: str) -> str:
        if _has_danger(user_text):
            return ("This sounds urgent. If anyone is in immediate danger, please contact "
                    "emergency services (Police helpline 15) right away. I can still help you "
                    "document what happened afterwards.")
        return ("Thank you for sharing that. I can help you understand your options, prepare "
                "a formal complaint, or check an existing one. Tell me a little more about "
                "what happened, or choose one of the options shown.")

    # Agent-facing convenience used by nodes for neutral prose generation.
    def compose(self, template: str, **kwargs) -> str:
        try:
            return template.format(**kwargs)
        except Exception:
            return template


def first_sentence(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    for sep in (".", "!", "?", "\n"):
        idx = text.find(sep)
        if idx > 0:
            return text[: idx + 1].strip()
    return text[:200]


def normalise_date(raw: str) -> str:
    raw = raw.strip().lower()
    today = datetime.now().date()
    words = {"yesterday", "today", "last night", "this morning", "last week"}
    if raw in words:
        offsets = {"yesterday": -1, "today": 0, "last night": -1, "this morning": 0, "last week": -7}
        from datetime import timedelta

        return (today + timedelta(days=offsets[raw])).isoformat()
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", raw)
    if m:
        d, mo, y = m.groups()
        y = int(y)
        if y < 100:
            y += 2000
        return f"{y:04d}-{int(mo):02d}-{int(d):02d}"
    return raw


def json_dumps(obj: dict) -> str:
    import json as _json

    return _json.dumps(obj, ensure_ascii=False)
