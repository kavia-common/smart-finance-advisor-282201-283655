#!/usr/bin/env python3
"""
Simple SQL migration runner for PostgreSQL (and compatible DBs).

Usage:
    python -m src.db.migrate
    or
    python src/db/migrate.py

Behavior:
- Discovers .sql files in src/db/migrations/ directory.
- Applies them in lexicographical order (e.g., 0001_*.sql, 0002_*.sql, ...).
- Splits files into individual statements safely using sqlparse (fallback to semicolon split if unavailable).
- Executes each statement in a transaction; on error, rolls back the file execution.
- Stores no migration state; idempotency is expected via 'IF NOT EXISTS' guards in SQL.

Environment:
- Requires DATABASE_URL to be set (e.g., postgresql+psycopg://user:pass@host:5432/dbname).
  If not set, falls back to default from src.core.config.get_settings() which may be sqlite, which also works
  for basic SQL files but is intended primarily for Postgres.

Note:
- For production-grade migrations, consider Alembic. This utility is a lightweight runner to bootstrap schema quickly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Try to use sqlparse for accurate splitting; it's optional.
try:
    import sqlparse  # type: ignore
except Exception:
    sqlparse = None  # type: ignore

# Local settings loader
try:
    from src.core.config import get_settings
except Exception:
    # Allow running the file in isolation
    def get_settings() -> dict:
        return {"DATABASE_URL": os.getenv("DATABASE_URL", "sqlite:///./finance.db")}


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _get_db_url() -> str:
    """Resolve the database URL from env/settings."""
    settings = get_settings()
    db_url = os.getenv("DATABASE_URL", settings.get("DATABASE_URL"))
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured. Set env var DATABASE_URL.")
    return db_url


def _create_engine(db_url: str) -> Engine:
    """Create SQLAlchemy engine with sensible defaults."""
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(db_url, pool_pre_ping=True, connect_args=connect_args)


def _read_sql_file(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def _split_sql_statements(sql: str) -> List[str]:
    """
    Split SQL script into statements.
    - Prefer sqlparse.split when available.
    - Fallback: naive split on semicolons.
    """
    if sqlparse is not None:
        parts = [s.strip() for s in sqlparse.split(sql)]
        return [p for p in parts if p]
    # Fallback: simplistic split
    parts = [p.strip() for p in sql.split(";")]
    # Remove empties and re-append missing semicolons not needed for execution with text()
    return [p for p in parts if p]


def _apply_sql_file(engine: Engine, path: Path) -> None:
    """Apply all statements from a single .sql file within a transaction."""
    content = _read_sql_file(path)
    statements = _split_sql_statements(content)
    if not statements:
        print(f"[SKIP] {path.name} (no statements)")
        return
    print(f"[APPLY] {path.name} ({len(statements)} statements)")
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def _discover_migrations(directory: Path) -> List[Path]:
    """Find .sql files in directory sorted lexicographically."""
    if not directory.exists():
        return []
    return sorted([p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".sql"], key=lambda p: p.name)


def main(argv: List[str] | None = None) -> int:
    """Entry point to run all SQL migrations."""
    argv = argv or sys.argv[1:]
    # Optional: allow passing a specific file or prefix in the future
    try:
        db_url = _get_db_url()
        engine = _create_engine(db_url)
        files = _discover_migrations(MIGRATIONS_DIR)
        if not files:
            print(f"[INFO] No migration files found in {MIGRATIONS_DIR}")
            return 0
        for f in files:
            _apply_sql_file(engine, f)
        print("[DONE] Migrations applied successfully.")
        return 0
    except Exception as exc:
        print(f"[ERROR] Migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
