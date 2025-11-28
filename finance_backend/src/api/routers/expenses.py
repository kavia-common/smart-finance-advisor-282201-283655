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

router = APIRouter(prefix="/expenses", tags=["transactions"])


class ExpenseCreate(BaseModel):
    """Payload for creating an expense entry."""
    date: date = Field(..., description="Transaction date (YYYY-MM-DD)")
    amount: float = Field(..., description="Expense amount (positive number)")
    category: str = Field(..., description="Category for the expense (e.g., Groceries)")
    description: Optional[str] = Field(None, description="Optional description")


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=TransactionSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create expense",
    description="Create a new expense transaction scoped to the authenticated user.",
)
def create_expense(
    payload: ExpenseCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TransactionSchema:
    """Create expense using transactions table with type='expense'.

    Note: Amounts are stored as negative or positive depending on dataset usage.
    For consistency with analytics that treat expenses as positive totals, we store
    the raw positive amount here and rely on 'type' to determine direction.
    """
    if payload.amount <= 0:
        raise HTTPException(status_code=422, detail="amount must be > 0 for expense")
    tx = Transaction(
        user_id=current_user.id,
        date=payload.date,
        amount=float(payload.amount),
        category=payload.category,
        description=payload.description,
        type="expense",
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[TransactionSchema],
    summary="List expenses",
    description="List user's expense transactions filtered optionally by month, year, and category.",
)
def list_expenses(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    month: Optional[int] = Query(None, ge=1, le=12, description="Month number (1-12)"),
    year: Optional[int] = Query(None, ge=1900, le=9999, description="Year (e.g., 2025)"),
    category: Optional[str] = Query(None, description="Filter by category (exact match)"),
) -> list[TransactionSchema]:
    """List expenses for the authenticated user with optional month/year/category filters."""
    conditions = [Transaction.user_id == current_user.id, Transaction.type == "expense"]
    if year is not None:
        conditions.append(and_(Transaction.date >= date(year, 1, 1), Transaction.date <= date(year, 12, 31)))
    if year is not None and month is not None:
        start = date(year, month, 1)
        next_month = month + 1
        next_year = year + 1 if next_month == 13 else year
        next_month = 1 if next_month == 13 else next_month
        end_exclusive = date(next_year, next_month, 1)
        conditions = [Transaction.user_id == current_user.id, Transaction.type == "expense",
                      Transaction.date >= start, Transaction.date < end_exclusive]
    if category is not None:
        conditions.append(Transaction.category == category)

    stmt = select(Transaction).where(and_(*conditions)).order_by(Transaction.date.asc(), Transaction.id.asc())
    return db.execute(stmt).scalars().all()


# PUBLIC_INTERFACE
@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete expense",
    description="Delete an expense transaction by ID (only if it belongs to the current user).",
    responses={404: {"description": "Expense not found"}, 204: {"description": "Deleted"}},
)
def delete_expense(
    id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Delete an expense transaction if owned by the authenticated user."""
    tx = db.get(Transaction, id)
    if tx is None or tx.type != "expense":
        raise HTTPException(status_code=404, detail="Expense not found")
    if tx.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(tx)
    db.commit()
    return None
