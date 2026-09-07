"""RAG ingestion: load demo markdown KB docs → chunk by heading/paragraph →
embed via the LLM abstraction → persist to kb_documents / kb_chunks.

Called at startup (first boot) and by the seed script. Re-ingesting the same
source_ref replaces its chunks, so the operation is idempotent.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.llm.client import get_llm_client
from app.models import KBChunk, KBDocument

# 5–10 short illustrative docs (spec §10). Clearly marked as demo guidance,
# not verified legal or official text.
KB_DOCS: list[dict] = [
    {
        "title": "Understanding police misconduct complaints (Demo guidance)",
        "source_ref": "kb/police_misconduct_overview.md",
        "content": """# Understanding police misconduct complaints

> This document is illustrative demo guidance for a hackathon prototype. It is NOT verified legal text.

Police misconduct generally covers behaviour by police officers that exceeds lawful
authority or violates professional standards. Common categories include rude or
discourteous behaviour, demanding bribes, unlawful detention, excessive force, and
refusing to register a First Information Report (FIR) without lawful reason.

In many jurisdictions a dedicated police complaints authority, or a citizen police
liaison office, receives these complaints. The complaint is normally assigned a
reference number, acknowledged, reviewed by an inquiry officer, and either resolved,
escalated to investigation, or closed with reasons recorded.

You do not need to prove your allegation at filing time. A complaint states what you
experienced and asks the authority to investigate. Making a false complaint knowingly,
however, can carry consequences, so describe events accurately and avoid guessing
details you are unsure about.""",
    },
    {
        "title": "Preserving evidence after an incident (Demo guidance)",
        "source_ref": "kb/preserve_evidence.md",
        "content": """# Preserving evidence after an incident

> This document is illustrative demo guidance for a hackathon prototype. It is NOT verified legal text.

Evidence is easiest to preserve immediately after an incident:

- Write down what happened while your memory is fresh, including date, time, and place.
- Keep original documents: medical slips, receipts, messages, call logs.
- Photograph visible injuries or property damage and keep the originals unedited;
  note where and when each photo was taken.
- Note the names or badge/belt numbers of officers involved if you saw them, and any
  witnesses with their contact details.
- Save any CCTV possibility: nearby shops or buildings may retain footage for only a
  few days, so ask early.

You may attach copies to your complaint. Always keep originals safely at home; only
hand over copies unless an authority formally requires originals.""",
    },
    {
        "title": "The general complaint filing process (Demo guidance)",
        "source_ref": "kb/filing_process.md",
        "content": """# The general complaint filing process

> This document is illustrative demo guidance for a hackathon prototype. It is NOT verified legal text.

A typical filing process looks like this:

1. Identify the authority that handles your issue category.
2. Gather the facts: what happened, when, where, who was involved, and any evidence.
3. Complete the complaint form or describe the incident to the receiving officer.
4. Receive an acknowledgment with a reference number.
5. Respond to any follow-up requests for additional information promptly.
6. Track the complaint status: received, under review, investigating, resolved or closed.

Deadlines can apply to certain categories, so filing sooner rather than later is
generally advisable. Keep your reference number safe; authorities use it to locate
your case in every future interaction.""",
    },
    {
        "title": "What happens after you submit (Demo guidance)",
        "source_ref": "kb/after_submission.md",
        "content": """# What happens after you submit a complaint

> This document is illustrative demo guidance for a hackathon prototype. It is NOT verified legal text.

After submission, authorities usually:

- Acknowledge receipt and issue a reference number (in this demo, instantly).
- Assign the case to an inquiry officer who may contact you for clarification.
- Possibly request additional documents — this is routine and not a rejection.
- Conduct an inquiry or investigation, which can involve hearing both sides.
- Communicate the outcome and record it against your reference number.

You can usually follow up using your reference number via a helpline, office visit,
or an online tracking facility. In this prototype, the assistant watches your
complaint's status on a schedule and notifies you in-app when anything changes.""",
    },
    {
        "title": "Your options when something goes wrong (Demo guidance)",
        "source_ref": "kb/understand_options.md",
        "content": """# Your options when something goes wrong

> This document is illustrative demo guidance for a hackathon prototype. It is NOT verified legal text.

You always have more than one option, and none of them commits you to anything:

- **Understand your options first.** Learn how the system typically handles issues
  like yours before deciding anything.
- **Report the incident.** Some people simply want the event on record. Reporting can
  be lighter-weight than a formal complaint.
- **File a formal complaint.** This triggers a documented review process with a
  reference number and a lifecycle you can track.
- **Not sure what to do?** That is a normal answer. Describing your situation to an
  advisor, a lawyer, or a trusted community resource is a valid step.

None of these options is a legal conclusion. This assistant provides neutral,
informational guidance only and does not decide what you should do.""",
    },
    {
        "title": "Police misconduct FAQ (Demo guidance)",
        "source_ref": "kb/police_faq.md",
        "content": """# Police misconduct complaints — FAQ

> This document is illustrative demo guidance for a hackathon prototype. It is NOT verified legal text.

**Do I need the officer's name to file?** No. Date, place, and a description of what
happened are the core facts. Badge numbers and names strengthen the complaint but are
optional — many people genuinely do not know them.

**Can I file anonymously?** Some authorities accept anonymous reports, but anonymous
complaints are harder to investigate and may receive no follow-up. Providing at least
a callback contact is generally encouraged.

**What if I fear retaliation?** Say so explicitly in your complaint. Authorities often
have confidentiality practices; this demo assistant also flags safety concerns
separately and urges contacting emergency services when there is immediate danger.

**Is there a fee?** In this demo, no. In real systems, complaint registration is
usually free; be wary of anyone demanding payment to "process" a complaint.""",
    },
    {
        "title": "Utility service complaints (Demo guidance)",
        "source_ref": "kb/utility_service.md",
        "content": """# Utility service complaints

> This document is illustrative demo guidance for a hackathon prototype. It is NOT verified legal text.

Electricity, water, gas and sanitation complaints usually go to the utility's own
consumer complaints cell first. Typical categories: excessive or estimated billing, a
faulty meter, prolonged outages, low voltage, low gas pressure, sewerage overflow and
garbage collection failures.

Have your consumer/account number ready — it is the fastest way for the utility to
locate your connection. A photograph of the bill or the meter reading is useful
evidence. If the utility does not resolve the complaint within its stated service
standard, escalation to the provincial ombudsman is a common next step in many
jurisdictions.""",
    },
    {
        "title": "Talking to authorities: practical tips (Demo guidance)",
        "source_ref": "kb/communication_tips.md",
        "content": """# Talking to authorities: practical tips

> This document is illustrative demo guidance for a hackathon prototype. It is NOT verified legal text.

- Be factual and specific: dates, times, places, and actions, not opinions.
- Stick to what you personally experienced; clearly separate what you were told by
  others from what you saw.
- Keep every acknowledgment, message, and reference number.
- Answer follow-up requests by the stated deadline; silence can close a case.
- Stay calm and courteous — it visibly helps, and it keeps the record clean.

This assistant separates what you report from what is verified so your complaint
record stays accurate and fair to everyone involved.""",
    },
]


def _split_chunks(md_text: str, target_chars: int = 1400) -> list[str]:
    """Split by headings, then pack paragraphs up to ~target_chars."""
    sections = re.split(r"\n(?=#{1,3} )", md_text.strip())
    chunks: list[str] = []
    buf: list[str] = []
    size = 0

    def flush():
        nonlocal buf, size
        if buf:
            chunks.append("\n".join(buf).strip())
            buf, size = [], 0

    for sec in sections:
        for para in [p for p in sec.split("\n\n") if p.strip()]:
            if size + len(para) > target_chars and buf:
                flush()
            buf.append(para)
            size += len(para)
    flush()
    return [c for c in chunks if len(c) > 40]


def ingest_kb(db: Session) -> dict:
    """Idempotent ingestion of the demo knowledge base."""
    llm = get_llm_client()
    doc_count, chunk_count = 0, 0
    for doc in KB_DOCS:
        existing = db.execute(
            select(KBDocument).where(KBDocument.source_ref == doc["source_ref"])
        ).scalar_one_or_none()
        if existing is None:
            existing = KBDocument(
                title=doc["title"], source_type="demo_kb", source_ref=doc["source_ref"]
            )
            db.add(existing)
            db.flush()
        else:
            # Replace chunks for idempotency.
            for ch in existing.chunks:
                db.delete(ch)
            db.flush()
            existing.title = doc["title"]
        chunks = _split_chunks(doc["content"])
        embeddings = llm.embed(chunks)
        for content, emb in zip(chunks, embeddings):
            db.add(
                KBChunk(
                    document_id=existing.id,
                    content=content,
                    embedding=emb,
                    metadata_={"source_ref": doc["source_ref"], "title": doc["title"]},
                )
            )
            chunk_count += 1
        doc_count += 1
    db.commit()
    return {"documents": doc_count, "chunks": chunk_count}
