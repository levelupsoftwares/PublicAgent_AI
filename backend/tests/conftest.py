"""pytest fixtures: isolated SQLite DB + mock providers per test session."""
from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ENV", "test")

_tmp = tempfile.mkdtemp(prefix="publicagent_test_")
# Force-override: the sandbox exports a foreign DATABASE_URL that would otherwise
# point tests at the live SQLite DB / mock-gov store.
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["FILE_STORAGE_LOCAL_DIR"] = _tmp
os.environ["LLM_PROVIDER"] = "mock"
os.environ["ENV"] = "test"


@pytest.fixture()
def db():
    """A fresh database per test (tables dropped & recreated)."""
    from app.db import Base, SessionLocal, engine
    import app.models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user(db):
    from app.api.auth import ensure_demo_user

    return ensure_demo_user(db)


@pytest.fixture()
def mock_gov(tmp_path):
    from app.gov.mock_client import MockGovernmentClient

    return MockGovernmentClient()


@pytest.fixture()
def seeded(db, user):
    from app.rag.ingest import ingest_kb

    ingest_kb(db)
    return db
