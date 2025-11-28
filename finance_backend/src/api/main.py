from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.db.session import Base, engine, get_db
from src.api.routers.seed import router as seed_router
from src.api.routers.transactions import router as transactions_router
from src.api.routers.budgets import router as budgets_router
from src.api.routers.goals import router as goals_router
from src.api.routers.analytics import router as analytics_router
from src.api.routers.alerts import router as alerts_router
from src.api.routers.advice import router as advice_router
# Use ensure_default_user from src.db.seed (module already present)
from src.db.seed import ensure_default_user
from sqlalchemy import text

# Initialize the FastAPI app with OpenAPI tags for documentation
app = FastAPI(
    title="Smart Finance Advisor Backend",
    description="Backend API for personal finance advisor. Provides endpoints for transactions, budgets, and goals.",
    version="0.1.0",
    openapi_tags=[
        {"name": "health", "description": "Health and status endpoints"},
        {"name": "transactions", "description": "Manage financial transactions"},
        {"name": "budgets", "description": "Set and retrieve budgets"},
        {"name": "goals", "description": "Savings goals and progress"},
        {"name": "analytics", "description": "Spending analytics and trends"},
        {"name": "alerts", "description": "Proactive alerts like overspending notifications"},
        {"name": "advice", "description": "Personalized savings and goals advice"},
        {"name": "seed", "description": "Demo data seeding operations"},
    ],
)

# Configure permissive CORS for development/demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Initialize database tables, apply baseline migrations for dev, and ensure default user exists."""
    Base.metadata.create_all(bind=engine)

    # Try to apply base SQL migrations (idempotent) for local dev/SQLite or first-run DBs.
    # This helps align schema with expected columns like users.password_hash.
    try:
        with engine.begin() as conn:
            # Apply 0001 (tables) and 0002 (indexes). IF NOT EXISTS guards keep this idempotent.
            conn.execute(text("""
            -- Users
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """))
            # Transactions table
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                date DATE NOT NULL,
                amount NUMERIC(12,2) NOT NULL,
                category VARCHAR(100) NOT NULL,
                description TEXT,
                type VARCHAR(20) NOT NULL DEFAULT 'expense',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """))
            # Budgets table
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                month VARCHAR(7) NOT NULL,
                category VARCHAR(100) NOT NULL,
                amount NUMERIC(12,2) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """))
            # Goals table
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name VARCHAR(150) NOT NULL,
                target_amount NUMERIC(12,2) NOT NULL,
                current_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                target_date DATE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """))
            # Ensure password_hash column exists if table was created earlier without it
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)"))

            # Helpful indexes (SQLite supports CREATE INDEX IF NOT EXISTS)
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions (user_id, date)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_transactions_user_category ON transactions (user_id, category)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_budgets_user_month ON budgets (user_id, month)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_goals_user_created_at ON goals (user_id, created_at)"))
    except Exception:
        # Best effort; if this fails (e.g., permissions/engine differences), continue with ORM-created tables.
        pass

    # Create default user for MVP single-user mode
    with next(get_db()) as db:
        ensure_default_user(db)


# Register routers
app.include_router(seed_router)
app.include_router(transactions_router)
app.include_router(budgets_router)
app.include_router(goals_router)
app.include_router(analytics_router)
app.include_router(alerts_router)
app.include_router(advice_router)


# PUBLIC_INTERFACE
@app.get("/", tags=["health"], summary="Health Check")
def health_check():
    """Health check endpoint to verify the service is running.

    Returns:
        JSON payload with a simple message.
    """
    return {"message": "Healthy"}


if __name__ == "__main__":
    # Allow running via: python -m src.api.main
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=3001, reload=False)
