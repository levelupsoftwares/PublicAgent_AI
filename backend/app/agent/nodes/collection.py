"""Progressive information collection: collect_information + validate_information.

The agent asks ONLY for what is still missing, one or two fields at a time, each
optional field carrying a [Skip] option. Answers arrive either as free text
(extracted via the LLM abstraction against the pending fields) or as structured
actions (skip / option / confirm) applied by the chat orchestrator before the
graph runs.

Validation failures NEVER loop internally: invalid values are cleared, the fields
are re-asked, and the graph ends the turn waiting for the citizen's correction.
"""
from __future__ import annotations

from app.agent.events import INFORMATION_REQUESTED, INFORMATION_VALIDATED
from app.agent.nodes.base import Services, emit, say
from app.agent.state import AgentState

SKIP_TOKEN = "__SKIPPED__"


def _field_status_list(state: AgentState) -> list[dict]:
    return [dict(f) for f in (state.get("required_information") or [])]


def _pending_questions(state: AgentState) -> list[dict]:
    """Fields that still need asking: required-missing first, then un-asked optional."""
    fields = _field_status_list(state)
    asked = set(state.get("asked_fields") or [])
    required_missing = [f for f in fields if f["required"] and f["status"] == "missing"]
    optional_pending = [
        f for f in fields if not f["required"] and f["status"] == "missing" and f["field"] not in asked
    ]
    return (required_missing + optional_pending)[:2]


def _status_by_name(fields: list[dict], name: str) -> bool:
    for f in fields:
        if f["field"] == name:
            return bool(f["required"])
    return False


def _apply_extracted(state: AgentState, fields_out: dict, required_information: list[dict]) -> dict:
    collected = dict(state.get("collected_information") or {})
    status_by_field = {f["field"]: f for f in required_information}
    for name, value in (fields_out or {}).items():
        if name not in status_by_field:
            continue
        if value == SKIP_TOKEN:
            collected[name] = SKIP_TOKEN
            status_by_field[name]["status"] = "skipped"
        elif isinstance(value, str) and value.strip():
            collected[name] = value.strip()
            status_by_field[name]["status"] = "provided"
    return collected


def make_collect_information(services: Services):
    def collect_information(state: AgentState) -> dict:
        required_information = _field_status_list(state)
        collected = dict(state.get("collected_information") or {})
        prev_asked = list(state.get("awaited_fields") or state.get("awaiting_fields") or [])
        asked_history = set(state.get("asked_fields") or [])

        # Smart prefill: the citizen's very first message usually IS the description.
        if (collected.get("description") in (None, "")) and state.get("initial_request"):
            collected["description"] = state["initial_request"][:800]
            for f in required_information:
                if f["field"] == "description":
                    f["status"] = "provided"

        # 1) If the citizen just answered free text, extract values for the fields
        #    we asked in the previous turn.
        if state.get("user_request") and prev_asked:
            try:
                prompt_lines = "\n".join(
                    f"- {name} ({'required' if _status_by_name(required_information, name) else 'optional'})"
                    for name in prev_asked
                )
                resp = services.llm.generate(
                    [{"role": "user", "content": state["user_request"][:1200]}],
                    system="[TASK: extract_fields] The citizen is answering questions for a "
                           f"complaint form. PENDING FIELDS:\n{prompt_lines}\n"
                           "Return JSON: {fields: {field_name: value}}. Use \"__SKIPPED__\" as "
                           "the value if they indicated they don't know / want to skip. Only "
                           "fill fields supported by their message.",
                    json_mode=True,
                )
                data = resp.json() or {}
                extracted = data.get("fields") or {}
            except Exception:
                extracted = {}
            # Mock fallback: single pending field takes the whole answer.
            if not extracted and len(prev_asked) == 1:
                txt = state["user_request"].strip()
                low = txt.lower()
                NEGATIONS = ("skip", "n/a", "na", "none", "unknown", "not sure", "no idea",
                             "don't know", "dont know", "do not know", "i don't know",
                             "i dont know", "i do not know", "no ")
                if any(low == n or low.startswith(n + " ") for n in NEGATIONS if n != "no ") \
                        or low in ("no",) or low.startswith("no, "):
                    extracted = {prev_asked[0]: SKIP_TOKEN}
                else:
                    extracted = {prev_asked[0]: txt[:300]}
            collected = _apply_extracted(state, extracted, required_information)

        # 2) What still needs asking?
        probe_state = {**state, "collected_information": collected,
                       "required_information": required_information}
        pending = _pending_questions(probe_state)
        if pending:
            questions = [
                {"field": f["field"], "label": f["label"], "type": f.get("type", "text"),
                 "required": f["required"], "allow_skip": not f["required"]}
                for f in pending
            ]
            asked_names = [q["field"] for q in questions]
            card = {
                "type": "information_request",
                "title": "A few details for your complaint",
                "progress": {
                    "provided": sum(1 for f in required_information if f["status"] == "provided"),
                    "total": len(required_information),
                },
                "questions": questions,
                "note": "Optional fields are marked — you can skip any of them.",
            }
            prose = ("Thanks. To prepare this correctly I only need a few more details — "
                     "answer what you can; optional fields can be skipped.")
            out = say(state, prose, card)
            out.update(emit(state, INFORMATION_REQUESTED, {"questions": asked_names}))
            out.update({
                "required_information": required_information,
                "collected_information": collected,
                "asked_fields": sorted(asked_history | set(asked_names)),
                "awaiting_fields": asked_names,
                "phase": "collecting",
            })
            return out

        # 3) Nothing left to ask — continue to validate_information via the edge.
        return {
            "required_information": required_information,
            "collected_information": collected,
            "asked_fields": sorted(asked_history),
            "awaiting_fields": [],
            "phase": "collecting",
        }

    return collect_information


def make_validate_information(services: Services):
    def validate_information(state: AgentState) -> dict:
        collected = dict(state.get("collected_information") or {})
        req = state.get("government_data") or {}
        requirements = req.get("requirements") or {}
        try:
            result = services.gov.validate_citizen_information(collected, requirements)
        except Exception:
            result = {"valid": True, "problems": [], "source": "mock"}

        problems = result.get("problems") or []
        if problems:
            # Clear invalid/missing values so they get re-asked next turn (no loops).
            required_information = _field_status_list(state)
            cleared = []
            for p in problems:
                for f in required_information:
                    if f["field"] == p["field"]:
                        f["status"] = "missing"
                collected.pop(p["field"], None)
                cleared.append(p["field"])
            card = {
                "type": "validation_issues",
                "title": "Let's fix a couple of details",
                "issues": [
                    {"field": p["field"], "issue": p["issue"],
                     "label": next((f["label"] for f in required_information
                                    if f["field"] == p["field"]), p["field"])}
                    for p in problems
                ],
            }
            out = say(state,
                      "I couldn't validate everything yet — I've highlighted the fields "
                      "that need another look. Nothing has been submitted.",
                      card)
            out.update(emit(state, INFORMATION_REQUESTED, {"revalidation": True,
                                                           "problems": problems}))
            out.update({
                "required_information": required_information,
                "collected_information": collected,
                "asked_fields": sorted(set(state.get("asked_fields") or []) | set(cleared)),
                "awaiting_fields": cleared,
                "phase": "collecting",
                "errors": [f"validation: {p['field']} {p['issue']}" for p in problems],
            })
            return out

        out = emit(state, INFORMATION_VALIDATED, {"validated": True})
        out["phase"] = "ready_for_review"
        return out

    return validate_information
