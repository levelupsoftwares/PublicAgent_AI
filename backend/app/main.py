"""PublicAgent AI — FastAPI application entry point.

- Serves the REST API under /api/*
- Optionally serves the built React frontend (frontend/dist) at / — this is how
  the sandbox preview runs on a single port; docker-compose instead runs the
  Vite/Node frontend container separately.
- Creates tables + ingests the demo KB + seeds demo data on first boot.
- Starts the APScheduler follow-up engine.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import Base, SessionLocal, engine

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("publicagent")


def _startup() -> None:
    # Announce the ACTIVE LLM provider on every boot. The silent
    # missing-key fallback to the offline mock was previously easy to miss —
    # this line makes the active engine impossible to overlook.
    from app.llm.client import get_llm_client

    logger.info("Active LLM provider: %s", get_llm_client().provider_name)

    # Import models so metadata is populated, then create tables.
    import app.models  # noqa: F401
    from sqlalchemy import inspect

    inspector = inspect(engine)
    if not inspector.has_table("users"):
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created")
    else:
        Base.metadata.create_all(bind=engine)  # idempotent

    # Demo knowledge base + seed data on first boot.
    from app.rag.ingest import ingest_kb, reingest_if_dim_changed
    from app.api.auth import ensure_demo_user

    db = SessionLocal()
    try:
        # If EMBEDDING_PROVIDER / EMBEDDING_DIM changed since the last run,
        # stored KB chunks have the wrong width and RAG silently returns
        # nothing (SQLite) or inserts fail (pgvector). Heal before anything
        # else touches the KB.
        if reingest_if_dim_changed(db):
            logger.info("Knowledge base re-ingested after embedding-dimension change")
        if not inspect(engine).has_table("kb_chunks") or db.execute(
            __import__("sqlalchemy").text("SELECT COUNT(*) FROM kb_chunks")
        ).scalar() == 0:
            stats = ingest_kb(db)
            logger.info("Knowledge base ingested: %s", stats)
        ensure_demo_user(db)
        db.commit()
    finally:
        db.close()

    import os

    if os.environ.get("SEED_ON_START", "0") not in ("0", "false", "False"):
        try:
            from app.scripts.seed_demo_data import seed_if_empty

            seeded = seed_if_empty()
            if seeded:
                logger.info("Demo data seeded")
        except Exception:
            # A seeding problem must never prevent the API from booting.
            logger.exception("Demo data seeding failed — continuing without "
                             "seeded demo complaints/conversations")

    # Follow-up scheduler (in-process; job state persisted in DB).
    from app.scheduler.followup_jobs import start_scheduler

    start_scheduler(SessionLocal)


def _shutdown() -> None:
    from app.scheduler.followup_jobs import stop_scheduler

    stop_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup()
    yield
    _shutdown()


app = FastAPI(
    title="PublicAgent AI",
    version="0.1.0",
    description="Agentic GovTech complaint assistant (hackathon MVP — demo/mock data only)",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:5173",
                   "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.auth import router as auth_router  # noqa: E402
from app.api.routes import api_router  # noqa: E402

app.include_router(auth_router)
app.include_router(api_router)


@app.get("/api/health", tags=["meta"])
def health():
    from app.llm.client import get_llm_client

    return {
        "status": "ok",
        "env": settings.ENV,
        "llm_provider": get_llm_client().provider_name,
        "database": engine.dialect.name,
        "notice": "All government data in this app is demo/mock data.",
    }


# ---------------------------------------------------------------------------
# Static frontend serving (sandbox single-port preview; optional in dev).
# ---------------------------------------------------------------------------
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"error": "not found"}, status_code=404)
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
