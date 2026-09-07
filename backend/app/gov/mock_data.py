"""Seed authorities, requirements and demo status thresholds for the mock client.

Every authority here is fictional and labelled "(Demo Data)" — this project is NOT
affiliated with any real government body. A secondary utility category proves the
abstraction generalizes beyond police misconduct (spec §9).
"""
from __future__ import annotations

MOCK_AUTHORITIES: list[dict] = [
    {
        "authority_id": "PPCA-DEMO",
        "name": "Provincial Police Complaints Authority (Demo Data)",
        "short_name": "PPCA (Demo)",
        "categories": ["police_misconduct"],
        "jurisdiction": "Punjab (Demo)",
        "contact": "ppca-demo@example.gov.demo",
        "description": "Demo authority that receives public complaints about police "
                       "misconduct, verifies allegations, and forwards cases to inquiry officers.",
    },
    {
        "authority_id": "CPLC-DEMO",
        "name": "Citizen Police Liaison Cell (Demo Data)",
        "short_name": "CPLC (Demo)",
        "categories": ["police_misconduct"],
        "jurisdiction": "Karachi Division (Demo)",
        "contact": "cplc-demo@example.gov.demo",
        "description": "Demo citizen-facing liaison cell that registers complaints and "
                       "coordinates with local police stations.",
    },
    {
        "authority_id": "ESD-CCC-DEMO",
        "name": "Electric Supply Company Consumer Complaints Cell (Demo Data)",
        "short_name": "ESD Complaints Cell (Demo)",
        "categories": ["utility_service"],
        "jurisdiction": "Regional (Demo)",
        "contact": "esd-demo@example.gov.demo",
        "description": "Demo consumer cell handling electricity billing, metering and "
                       "outage complaints.",
    },
]

# Field-level requirements per category. required=False fields always offer [Skip].
MOCK_REQUIREMENTS: dict[str, dict] = {
    "police_misconduct": {
        "authority_id": "PPCA-DEMO",
        "category": "police_misconduct",
        "fields": [
            {"field": "complainant_name", "label": "Your full name", "type": "text",
             "required": True, "ask": "May I have your full name as it should appear on the complaint?"},
            {"field": "incident_date", "label": "Date of incident", "type": "date",
             "required": True, "ask": "On what date did the incident happen? (e.g. 2026-01-14 or 'yesterday')"},
            {"field": "incident_time", "label": "Approximate time", "type": "text",
             "required": False, "ask": "Roughly what time did it happen? (you can skip this)"},
            {"field": "location", "label": "Location of incident", "type": "text",
             "required": True, "ask": "Where did the incident take place? (area/landmark is fine)"},
            {"field": "police_station", "label": "Police station involved", "type": "text",
             "required": True, "ask": "Which police station or checkpost was involved?"},
            {"field": "officer_name", "label": "Officer's name (if known)", "type": "text",
             "required": False, "ask": "Do you know the officer's name? It's optional — you can skip."},
            {"field": "officer_badge_number", "label": "Badge / belt number (if known)", "type": "text",
             "required": False, "ask": "Do you have the officer's badge or belt number? Optional — skip is fine."},
            {"field": "description", "label": "What happened", "type": "textarea",
             "required": True, "ask": "In a few sentences, what exactly happened?"},
            {"field": "complainant_phone", "label": "Contact phone", "type": "tel",
             "required": True, "ask": "What phone number should the authority use to reach you?"},
        ],
        "evidence_guidance": "Photos, audio, medical reports or witness contacts help, but are not mandatory.",
        "sla_note": "Demo SLA: acknowledgment within minutes (accelerated for this demo).",
    },
    "utility_service": {
        "authority_id": "ESD-CCC-DEMO",
        "category": "utility_service",
        "fields": [
            {"field": "complainant_name", "label": "Your full name", "type": "text",
             "required": True, "ask": "May I have your full name?"},
            {"field": "account_number", "label": "Consumer / account number", "type": "text",
             "required": True, "ask": "What is your consumer/account number?"},
            {"field": "incident_date", "label": "When did the issue start", "type": "date",
             "required": True, "ask": "When did the problem start?"},
            {"field": "location", "label": "Service address / area", "type": "text",
             "required": True, "ask": "What is the service address or area?"},
            {"field": "description", "label": "Describe the issue", "type": "textarea",
             "required": True, "ask": "Briefly describe the problem (billing, outage, meter…)."},
        ],
        "evidence_guidance": "A photo of the bill or meter speeds up verification.",
        "sla_note": "Demo SLA: 3 working days (accelerated for this demo).",
    },
    "general_grievance": {
        "authority_id": "PPCA-DEMO",
        "category": "general_grievance",
        "fields": [
            {"field": "complainant_name", "label": "Your full name", "type": "text",
             "required": True, "ask": "May I have your full name?"},
            {"field": "incident_date", "label": "Date of incident", "type": "date",
             "required": True, "ask": "When did this happen?"},
            {"field": "location", "label": "Location", "type": "text",
             "required": True, "ask": "Where did this happen?"},
            {"field": "description", "label": "What happened", "type": "textarea",
             "required": True, "ask": "Describe what happened in a few sentences."},
        ],
        "evidence_guidance": "Any supporting documents are optional.",
        "sla_note": "Demo SLA: varies (accelerated for this demo).",
    },
}

# Lifecycle order used by the mock status engine and force-advance endpoint.
STATUS_ORDER = [
    "submitted",
    "received",
    "under_review",
    "investigating",
    "resolved",
]

STATUS_DISPLAY = {
    "draft": "Draft",
    "submitted": "Submitted",
    "received": "Received",
    "under_review": "Under Review",
    "additional_info_required": "Additional Info Required",
    "investigating": "Investigating",
    "resolved": "Resolved",
    "closed": "Closed",
}
