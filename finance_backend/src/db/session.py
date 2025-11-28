from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from src.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def _build_engine_url() -> str:
    settings = get_settings()
    return settings["DATABASE_URL"]


def _engine_connect_args(db_url: str) -> dict:
    """Provide driver-specific connect_args."""
    # SQLite requires check_same_thread=False in typical FastAPI threaded runtimes
    if db_url.startswith("sqlite"):
        return {"check_same_thread": False}
    # For Postgres or others, rely on defaults
    return {}


# Build engine with safe defaults:
# - echo disabled (no noisy SQL logs in production)
# - pool_pre_ping True (detect stale connections e.g., Postgres idles)
DATABASE_URL = _build_engine_url()
engine = create_engine(
    DATABASE_URL,
    connect_args=_engine_connect_args(DATABASE_URL),
    pool_pre_ping=True,
    echo=False,
)

# Session factory for request-scoped DB sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# PUBLIC_INTERFACE
def get_db():
    """FastAPI dependency that yields a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
