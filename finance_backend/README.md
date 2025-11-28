# Smart Finance Advisor - Backend

This is the FastAPI backend for the Smart Finance Advisor.

## Database Migrations (PostgreSQL/SQLite)

A lightweight SQL migration runner is included.

- Place SQL files in `src/db/migrations/` using numeric prefixes (e.g., `0001_init.sql`, `0002_indexes.sql`).
- To apply all migrations (in order) against your `DATABASE_URL`:

  1. Ensure the environment variable `DATABASE_URL` is set (e.g., `postgresql+psycopg://USER:PASS@HOST:5432/DBNAME` or `sqlite:///./finance.db`).
  2. Run:
     ```
     python -m src.db.migrate
     ```
     or
     ```
     python src/db/migrate.py
     ```

Startup behavior:
- On app startup, we now:
  - Create ORM tables if missing.
  - Attempt to run migrations `0001` and `0002` using the built-in runner (idempotent).
  - If the runner isn't available, apply a minimal inline schema (idempotent) and ensure indexes.
  - As a final safety for legacy SQLite DBs, if `users.password_hash` column is missing, we add it via `ALTER TABLE`.

This avoids OperationalError on startup due to schema mismatches in older local SQLite files.

Notes:
- The runner executes each file in a transaction; if any statement fails, the file is rolled back.
- Use `IF NOT EXISTS` guards in your SQL for idempotency since this runner does not keep migration state.
- For production-grade workflows, consider using Alembic. This runner is provided for bootstrapping and simplicity.

### Schema overview

- users: id, email (UNIQUE), password_hash (nullable for demo), created_at, updated_at
- transactions: user_id FK, date, amount, category, description, type, timestamps
- budgets: unique by (user_id, month, category)
- goals: user-scoped savings goals with optional target_date

All queries in routers/services are already scoped by `user_id` (MVP uses `user_id=1`).

## Environment

- Required: `DATABASE_URL` (falls back to `sqlite:///./finance.db` for local development).
- PostgreSQL example: `postgresql+psycopg://user:password@localhost:5432/finance_db`.

## Dependencies

- SQLAlchemy is used for DB connections and ORM.
- Optional: `sqlparse` for better SQL splitting when running migrations (already included in `requirements.txt`).

OperationalError resilience:
- On older databases lacking `users.password_hash`, the app will:
  - Run migrations if possible.
  - Otherwise, add the column for SQLite via `ALTER TABLE users ADD COLUMN password_hash TEXT NULL`.
  - And the `ensure_default_user` seeding logic introspects table columns and inserts without selecting/inserting the missing column to avoid startup failures.
