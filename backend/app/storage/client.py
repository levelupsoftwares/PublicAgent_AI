"""StorageClient abstraction — local disk in dev, Alibaba OSS adapter stubbed."""
from __future__ import annotations

from typing import BinaryIO, Protocol, runtime_checkable


@runtime_checkable
class StorageClient(Protocol):
    def save(self, key: str, data: BinaryIO, content_type: str) -> str: ...
    def open(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def public_url(self, key: str) -> str | None: ...


_client = None


def get_storage_client() -> StorageClient:
    global _client
    if _client is None:
        from app.config import settings

        if settings.FILE_STORAGE_BACKEND.lower() == "oss":
            from app.storage.oss import AlibabaOSSStorage

            _client = AlibabaOSSStorage()
        else:
            from app.storage.local import LocalDiskStorage

            _client = LocalDiskStorage()
    return _client


def set_storage_client(client) -> None:
    global _client
    _client = client
