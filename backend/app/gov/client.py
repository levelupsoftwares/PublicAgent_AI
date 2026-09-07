"""GovernmentServiceClient — the abstraction every consumer depends on (spec §9).

The agent layer must only import this Protocol, never MockGovernmentClient, so a
real integration can later be swapped in without touching agent code.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GovernmentServiceClient(Protocol):
    def find_authority(self, issue_type: str, location: str | None) -> dict: ...
    def get_complaint_requirements(self, authority_id: str, category: str) -> dict: ...
    def validate_citizen_information(self, data: dict, requirements: dict) -> dict: ...
    def submit_complaint(self, payload: dict) -> dict: ...
    def get_complaint_status(self, reference_number: str) -> dict: ...
    def get_complaint_details(self, reference_number: str) -> dict: ...


_client = None


def get_gov_client() -> GovernmentServiceClient:
    """Factory. Today: MockGovernmentClient. Later: a real client via env var."""
    global _client
    if _client is None:
        from app.gov.mock_client import MockGovernmentClient

        _client = MockGovernmentClient()
    return _client


def set_gov_client(client) -> None:
    global _client
    _client = client
