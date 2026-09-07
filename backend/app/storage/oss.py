"""Alibaba Cloud OSS storage adapter — deliberately a clearly-marked stub.

The interface is wired (importable, selectable via FILE_STORAGE_BACKEND=oss) so
production wiring is a contained change: fill in the four methods with oss2 SDK
calls and provide OSS_* credentials in .env. It is intentionally NOT fully
implemented for the hackathon MVP (documented in DECISIONS.md).
"""
from __future__ import annotations

from typing import BinaryIO

from app.config import settings


class AlibabaOSSStorage:
    """Stub — raises with a clear message; never silently pretends to work."""

    def __init__(self):
        self.endpoint = settings.OSS_ENDPOINT if hasattr(settings, "OSS_ENDPOINT") else ""
        self.bucket = getattr(settings, "OSS_BUCKET", "")
        self.access_key_id = getattr(settings, "OSS_ACCESS_KEY_ID", "")
        if not (self.endpoint and self.bucket and self.access_key_id):
            # Keep construction cheap; real calls will fail loudly instead.
            self._configured = False
        else:
            self._configured = False  # SDK wiring intentionally deferred

    def _not_wired(self):
        raise NotImplementedError(
            "AlibabaOSSStorage is a stub in this MVP. Set FILE_STORAGE_BACKEND=local "
            "or implement oss.py against the oss2 SDK before enabling OSS."
        )

    def save(self, key: str, data: BinaryIO, content_type: str) -> str:
        self._not_wired()

    def open(self, key: str) -> bytes:
        self._not_wired()

    def delete(self, key: str) -> None:
        self._not_wired()

    def public_url(self, key: str) -> str | None:
        self._not_wired()
