from __future__ import annotations

from datetime import date
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.db.models import Transaction, User
from src.db.schemas import Transaction as TransactionSchema
from src.db.session import get_db

router = APIRouter(prefix="/income", tags=["transactions"])


class IncomeCreate(BaseModel):
    """Payload for creating an income entry."""
    date: date = Field(..., description="Transaction date (YYYY-MM-DD)")
    amount: float = Field(..., description="Income amount (positive number)")
    category: str = Field(..., description="Category for the income (e.g., Salary)")
    description: Optional[str] = Field(None, description="Optional description")


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=TransactionSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create income",
    description="Create a new income transaction scoped to the authenticated user.",
)
def create_income(
    payload: IncomeCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TransactionSchema:
    """Create income using transactions table with type='income'."""
    if payload.amount <= 0:
        raise HTTPException(status_code=422, detail="amount must be > 0 for income")
    tx = Transaction(
        user_id=current_user.id,
        date=payload.date,
        amount=float(payload.amount),
        category=payload.category,
        description=payload.description,
        type="income",
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[TransactionSchema],
    summary="List income",
    description="List user's income transactions filtered optionally by month and year.",
)
def list_income(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    month: Optional[int] = Query(None, ge=1, le=12, description="Month number (1-12)"),
    year: Optional[int] = Query(None, ge=1900, le=9999, description="Year (e.g., 2025)"),
) -> list[TransactionSchema]:
    """List income transactions for the authenticated user with optional month/year filters."""
    conditions = [Transaction.user_id == current_user.id, Transaction.type == "income"]
    if year is not None:
        conditions.append(and_(Transaction.date >= date(year, 1, 1), Transaction.date <= date(year, 12, 31)))
    if year is not None and month is not None:
        # Narrow to the month by adding simple month equality via BETWEEN
        # Use first day and last day heuristics: < next month start
        start = date(year, month, 1)
        next_month = month + 1
        next_year = year + 1 if next_month == 13 else year
        next_month = 1 if next_month == 13 else next_month
        end_exclusive = date(next_year, next_month, 1)
        # Replace year-only condition with precise month condition
        conditions = [Transaction.user_id == current_user.id, Transaction.type == "income",
                      Transaction.date >= start, Transaction.date < end_exclusive]

    stmt = select(Transaction).where(and_(*conditions)).order_by(Transaction.date.asc(), Transaction.id.asc())
    return db.execute(stmt).scalars().all()


# PUBLIC_INTERFACE
@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete income",
    description="Delete an income transaction by ID (only if it belongs to the current user).",
    responses={404: {"description": "Income not found"}, 204: {"description": "Deleted"}},
)
def delete_income(
    id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Delete an income transaction if owned by the authenticated user."""
    tx = db.get(Transaction, id)
    if tx is None or tx.type != "income":
        raise HTTPException(status_code=404, detail="Income not found")
    if tx.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(tx)
    db.commit()
    return None
