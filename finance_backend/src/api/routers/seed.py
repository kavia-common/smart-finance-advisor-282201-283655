from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db.seed import clear_demo_data, load_demo_data
from src.db.session import get_db

router = APIRouter(
    prefix="/seed/demo",
    tags=["seed"],
)


class SeedLoadRequest(BaseModel):
    months_back: int = Field(6, description="Number of months back to generate, including current month")
    approx_total: int = Field(500, description="Approximate total number of transactions to generate")
    random_seed: int | None = Field(42, description="Optional random seed (set null for non-deterministic)")


class SeedResponse(BaseModel):
    message: str = Field(..., description="Human readable status")
    details: dict = Field(default_factory=dict, description="Seeding summary details")


# PUBLIC_INTERFACE
@router.post(
    "/load",
    summary="Load demo data",
    description="Generate demo transactions for the last N months. Idempotent: clears existing demo transactions before loading.",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Demo data loaded", "model": SeedResponse},
        400: {"description": "Invalid parameters"},
        500: {"description": "Internal error"},
    },
)
def load_demo(
    payload: SeedLoadRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SeedResponse:
    """Create demo data for development and demos.

    Args:
        payload: Parameters controlling how much data to generate.
        db: Injected SQLAlchemy session.

    Returns:
        SeedResponse containing summary details.
    """
    if payload.months_back <= 0 or payload.months_back > 24:
        raise HTTPException(status_code=400, detail="months_back must be between 1 and 24")
    if payload.approx_total <= 0 or payload.approx_total > 5000:
        raise HTTPException(status_code=400, detail="approx_total must be between 1 and 5000")

    details = load_demo_data(
        db=db,
        months_back=payload.months_back,
        approx_total=payload.approx_total,
        random_seed=payload.random_seed,
    )
    return SeedResponse(message="Demo data loaded", details=details)


# PUBLIC_INTERFACE
@router.delete(
    "/clear",
    summary="Clear demo data",
    description="Remove all demo transactions for the default user. Safe to call multiple times.",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Demo data cleared", "model": SeedResponse},
        500: {"description": "Internal error"},
    },
)
def clear_demo(
    db: Annotated[Session, Depends(get_db)],
) -> SeedResponse:
    """Delete demo transactions for the default demo user."""
    deleted = clear_demo_data(db)
    return SeedResponse(message="Demo data cleared", details={"deleted": deleted})
