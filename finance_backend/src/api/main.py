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
    """Initialize database tables and ensure default user exists."""
    Base.metadata.create_all(bind=engine)
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
