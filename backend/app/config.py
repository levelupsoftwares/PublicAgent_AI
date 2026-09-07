"""Central configuration, loaded from environment variables (.env supported)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent  # /backend


class Settings(BaseSettings):
    # --- Core ---
    ENV: str = "development"
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'data' / 'publicagent.db'}"
    PORT: int = 8000

    # --- LLM provider abstraction ---
    # model_studio | openai_compatible | groq | mock
    LLM_PROVIDER: str = "model_studio"
    LLM_MODEL_NAME: str = "qwen-plus"
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    OPENAI_BASE_URL: str = ""
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL_NAME: str = "text-embedding-v3"
    EMBEDDING_DIM: int = 1536

    # --- Groq (LLM_PROVIDER=groq) ---
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    # Default to qwen3-32b — closest Groq-hosted Qwen3 model to the requested
    # qwen3-27b (no such version exists on Groq; override via env if needed).
    GROQ_MODEL_NAME: str = "qwen/qwen3-32b"

    # --- OpenRouter (used for embeddings when LLM_PROVIDER=groq) ---
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # --- Auth ---
    JWT_SECRET: str = "change-me-in-production"
    JWT_EXPIRE_MINUTES: int = 60

    # --- Background jobs ---
    FOLLOWUP_CHECK_INTERVAL_SECONDS: int = 120

    # --- File storage ---
    FILE_STORAGE_BACKEND: str = "local"  # local | oss
    FILE_STORAGE_LOCAL_DIR: str = str(BASE_DIR / "uploads")
    MAX_UPLOAD_MB: int = 10

    # --- CORS / frontend ---
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # --- RAG ---
    RAG_TOP_K: int = 4

    # --- Mock government API demo timings ---
    MOCK_STATUS_RECEIVED_AFTER_SECONDS: int = 30
    MOCK_STATUS_UNDER_REVIEW_AFTER_SECONDS: int = 90
    MOCK_STATUS_INVESTIGATING_AFTER_SECONDS: int = 180
    MOCK_STATUS_RESOLVED_AFTER_SECONDS: int = 300

    class Config:
        env_file = (BASE_DIR.parent / ".env").as_posix()  # repo-root .env
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # The sandbox exports a foreign DATABASE_URL (e.g. "file:...") for other tooling;
    # SQLAlchemy only understands sqlite/postgresql/etc. so fall back to our default.
    valid_schemes = ("sqlite", "postgresql", "postgres", "mysql", "oracle", "mssql")
    if not s.DATABASE_URL.lower().startswith(valid_schemes):
        s.DATABASE_URL = f"sqlite:///{BASE_DIR / 'data' / 'publicagent.db'}"
    # Ensure local storage dirs exist early.
    Path(s.FILE_STORAGE_LOCAL_DIR).mkdir(parents=True, exist_ok=True)
    if s.DATABASE_URL.startswith("sqlite:///"):
        db_path = s.DATABASE_URL.replace("sqlite:///", "", 1)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()
