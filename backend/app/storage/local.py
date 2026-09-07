"""Local-disk storage implementation (dev/demo)."""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from app.config import settings


def _safe_key(key: str) -> Path:
    base = Path(settings.FILE_STORAGE_LOCAL_DIR).resolve()
    p = (base / key).resolve()
    if not str(p).startswith(str(base)):
        raise ValueError("Invalid storage key (path traversal attempt).")
    return p


class LocalDiskStorage:
    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.FILE_STORAGE_LOCAL_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: BinaryIO, content_type: str) -> str:
        dest = _safe_key(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            shutil.copyfileobj(data, fh)
        return key

    def open(self, key: str) -> bytes:
        return _safe_key(key).read_bytes()

    def delete(self, key: str) -> None:
        p = _safe_key(key)
        if p.exists():
            p.unlink()

    def public_url(self, key: str) -> str | None:
        return f"/api/evidence/file/{key}"


def build_object_key(user_id: str, filename: str) -> str:
    ext = Path(filename).suffix.lower()[:8]
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", Path(filename).stem)[:60]
    return f"{user_id}/{uuid.uuid4().hex}_{safe_name}{ext}"
