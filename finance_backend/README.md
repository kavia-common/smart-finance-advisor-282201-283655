# Smart Finance Advisor - Backend

This is the FastAPI backend for the Smart Finance Advisor.

## Database Migrations (PostgreSQL)

A lightweight SQL migration runner is included.

- Place SQL files in `src/db/migrations/` using numeric prefixes (e.g., `0001_init.sql`, `0002_indexes.sql`).
- To apply all migrations (in order) against your `DATABASE_URL`:

  1. Ensure the environment variable `DATABASE_URL` is set (e.g., `postgresql+psycopg://USER:PASS@HOST:5432/DBNAME`).
  2. Run:
     ```
     python -m src.db.migrate
     ```
     or
     ```
     python src/db/migrate.py
     ```

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
