"""SQLAlchemy engine/session setup.

Supports PostgreSQL (with pgvector) in the docker-compose deployment and SQLite
as a zero-infra fallback for local/dev runs. The vector store strategy is chosen
at runtime in app/rag/retriever.py based on the same DATABASE_URL.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _make_engine():
    url = settings.DATABASE_URL
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Session:
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_postgres() -> bool:
    return engine.dialect.name == "postgresql"
