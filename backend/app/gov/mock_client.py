"""MockGovernmentClient — a believable, clearly-labelled fake government API.

Behaviours (spec §9):
- find_authority / requirements / submit / status / details against fictional
  "(Demo Data)" authorities; every response carries source: "mock".
- submit_complaint is idempotent per idempotency_key (client-generated GUID for a
  draft) — retries never create duplicate cases.
- get_complaint_status advances automatically with elapsed time so a live demo
  shows real progression in minutes (thresholds via env, defaults 30s/90s/180s/300s).
- A file-backed case store (data/mock_gov_store.json) survives restarts.
"""
from __future__ import annotations

import json
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings
from app.gov.mock_data import MOCK_AUTHORITIES, MOCK_REQUIREMENTS, STATUS_ORDER

def _default_store_path() -> Path:
    import os

    if os.environ.get("MOCK_STORE_PATH"):
        return Path(os.environ["MOCK_STORE_PATH"])
    if settings.DATABASE_URL.startswith("sqlite"):
        return Path(settings.DATABASE_URL.replace("sqlite:///", "", 1)).parent / "mock_gov_store.json"
    return Path("./data/mock_gov_store.json")


STORE_PATH = _default_store_path()

_LOCK = threading.RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts)


class MockGovernmentClient:
    source = "mock"

    # ------------------------------------------------------------ case store
    def _load(self) -> dict:
        with _LOCK:
            if not STORE_PATH.exists():
                return {"cases": {}, "seq": 1928}
            try:
                return json.loads(STORE_PATH.read_text())
            except Exception:
                return {"cases": {}, "seq": 1928}

    def _save(self, store: dict) -> None:
        with _LOCK:
            STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STORE_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=False))

    # -------------------------------------------------------------- interface
    def find_authority(self, issue_type: str, location: str | None = None) -> dict:
        matches = [a for a in MOCK_AUTHORITIES if issue_type in a["categories"]]
        if not matches:
            matches = [MOCK_AUTHORITIES[0]]
        auth = matches[0]
        return {
            "source": "mock",
            "authority": {
                "authority_id": auth["authority_id"],
                "name": auth["name"],
                "short_name": auth["short_name"],
                "jurisdiction": auth["jurisdiction"],
                "contact": auth["contact"],
                "description": auth["description"],
            },
            "note": "Demo / Mock government data — not a verified real institution.",
        }

    def get_complaint_requirements(self, authority_id: str, category: str) -> dict:
        req = MOCK_REQUIREMENTS.get(category) or MOCK_REQUIREMENTS["general_grievance"]
        out = dict(req)
        out["source"] = "mock"
        out["note"] = "Demo / Mock government data — not a verified real institution."
        return out

    def validate_citizen_information(self, data: dict, requirements: dict) -> dict:
        problems: list[dict] = []
        for f in requirements.get("fields", []):
            name, required = f["field"], f["required"]
            val = data.get(name)
            skipped = val == "__SKIPPED__" or val is None or (isinstance(val, str) and not val.strip())
            if required and skipped:
                problems.append({"field": name, "issue": "required_field_missing"})
        # Plausibility checks
        import re

        if data.get("incident_date") and data["incident_date"] != "__SKIPPED__":
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(data["incident_date"])):
                problems.append({"field": "incident_date", "issue": "invalid_date_format"})
        if data.get("complainant_phone") and data["complainant_phone"] != "__SKIPPED__":
            if not re.match(r"^(\+92|0)?3\d{2}[- ]?\d{7}$", str(data["complainant_phone"])):
                problems.append({"field": "complainant_phone", "issue": "phone_format_unexpected"})
        return {
            "source": "mock",
            "valid": len(problems) == 0,
            "problems": problems,
        }

    def submit_complaint(self, payload: dict) -> dict:
        store = self._load()
        idem = payload.get("idempotency_key")
        with _LOCK:
            if idem:
                for case in store["cases"].values():
                    if case.get("idempotency_key") == idem:
                        return self._submission_result(case, duplicate=True)
            store["seq"] = int(store.get("seq", 1928)) + random.randint(1, 3)
            ref = f"CMP-{datetime.now().year}-{store['seq']:06d}"
            submitted_at = _now()
            store["cases"][ref] = {
                "reference_number": ref,
                "idempotency_key": idem,
                "category": payload.get("category"),
                "department": payload.get("department"),
                "jurisdiction": payload.get("jurisdiction"),
                "description": payload.get("description"),
                "structured_fields": payload.get("structured_fields", {}),
                "submitted_at": _iso(submitted_at),
                "explicit_status_override": None,
                "history": [{"status": "submitted", "at": _iso(submitted_at), "note": "Complaint registered"}],
            }
            self._save(store)
        return self._submission_result(store["cases"][ref])

    def _submission_result(self, case: dict, duplicate: bool = False) -> dict:
        return {
            "source": "mock",
            "reference_number": case["reference_number"],
            "status": "submitted",
            "submitted_at": case["submitted_at"],
            "duplicate": duplicate,
            "note": "Demo / Mock government data — no real complaint was filed anywhere.",
        }

    def get_complaint_status(self, reference_number: str) -> dict:
        store = self._load()
        case = store["cases"].get(reference_number)
        if not case:
            return {"source": "mock", "found": False,
                    "error": f"Reference {reference_number} not found in demo registry."}
        status = self._computed_status(case)
        return {
            "source": "mock",
            "found": True,
            "reference_number": reference_number,
            "status": status,
            "submitted_at": case["submitted_at"],
            "history": case.get("history", []),
            "note": "Demo / Mock government data.",
        }

    def get_complaint_details(self, reference_number: str) -> dict:
        store = self._load()
        case = store["cases"].get(reference_number)
        if not case:
            return {"source": "mock", "found": False, "error": "not_found"}
        out = {"source": "mock", "found": True, **case}
        out["status"] = self._computed_status(case)
        return out

    # ------------------------------------------------------------ demo helpers
    def force_advance(self, reference_number: str) -> dict:
        """Demo safety-net: jump a case to its next lifecycle status immediately."""
        store = self._load()
        case = store["cases"].get(reference_number)
        if not case:
            return {"source": "mock", "found": False, "error": "not_found"}
        with _LOCK:
            current = self._computed_status(case)
            try:
                idx = STATUS_ORDER.index(current)
            except ValueError:
                idx = 0
            nxt = STATUS_ORDER[min(idx + 1, len(STATUS_ORDER) - 1)]
            case["explicit_status_override"] = nxt
            case["override_at"] = _iso(_now())
            case["history"].append({"status": nxt, "at": _iso(_now()),
                                    "note": "Advanced via demo force-advance endpoint"})
            self._save(store)
        return {"source": "mock", "found": True, "reference_number": reference_number,
                "status": nxt, "previous": current, "note": "Demo / Mock government data."}

    def seed_case(self, reference_number: str, *, submitted_at: datetime,
                  category: str, department: str, jurisdiction: str | None,
                  description: str, structured_fields: dict, idempotency_key: str | None = None,
                  status_override: str | None = None) -> dict:
        """Used by the seed script (and tests) to pre-register a case."""
        store = self._load()
        with _LOCK:
            store["cases"][reference_number] = {
                "reference_number": reference_number,
                "idempotency_key": idempotency_key,
                "category": category,
                "department": department,
                "jurisdiction": jurisdiction,
                "description": description,
                "structured_fields": structured_fields,
                "submitted_at": _iso(submitted_at),
                "explicit_status_override": status_override,
                "override_at": _iso(_now()) if status_override else None,
                "history": [
                    {"status": "submitted", "at": _iso(submitted_at), "note": "Complaint registered"},
                    {"status": "received", "at": _iso(submitted_at + timedelta(seconds=30)),
                     "note": "Acknowledged by authority"},
                    {"status": "under_review", "at": _iso(submitted_at + timedelta(seconds=90)),
                     "note": "Assigned to an inquiry officer"},
                ],
            }
            self._save(store)
        return store["cases"][reference_number]

    # --------------------------------------------------------- status machine
    def _computed_status(self, case: dict) -> str:
        if case.get("explicit_status_override"):
            return case["explicit_status_override"]
        submitted = _parse(case.get("submitted_at"))
        if not submitted:
            return "submitted"
        elapsed = (_now() - submitted).total_seconds()
        thresholds = [
            ("resolved", settings.MOCK_STATUS_RESOLVED_AFTER_SECONDS),
            ("investigating", settings.MOCK_STATUS_INVESTIGATING_AFTER_SECONDS),
            ("under_review", settings.MOCK_STATUS_UNDER_REVIEW_AFTER_SECONDS),
            ("received", settings.MOCK_STATUS_RECEIVED_AFTER_SECONDS),
        ]
        for status, seconds in thresholds:
            if elapsed >= seconds:
                return status
        return "submitted"


def mock_status_target_seconds() -> dict[str, int]:
    return {
        "received": settings.MOCK_STATUS_RECEIVED_AFTER_SECONDS,
        "under_review": settings.MOCK_STATUS_UNDER_REVIEW_AFTER_SECONDS,
        "investigating": settings.MOCK_STATUS_INVESTIGATING_AFTER_SECONDS,
        "resolved": settings.MOCK_STATUS_RESOLVED_AFTER_SECONDS,
    }
