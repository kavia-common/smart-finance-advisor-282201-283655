import os
from functools import lru_cache

# PUBLIC_INTERFACE
def get_env(key: str, default: str | None = None) -> str | None:
    """Get environment variable value with optional default."""
    return os.getenv(key, default)

# PUBLIC_INTERFACE
@lru_cache(maxsize=1)
def get_settings() -> dict:
    """Return application settings loaded from environment.

    Settings:
      - DATABASE_URL: SQLAlchemy connection string.
        Defaults to sqlite:///./finance.db for local development.
        Example for PostgreSQL: postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME
    """
    # Default to local sqlite for dev. Use env to switch to Postgres in deployed envs.
    db_url = get_env("DATABASE_URL", "sqlite:///./finance.db")
    return {
        "DATABASE_URL": db_url,
    }
