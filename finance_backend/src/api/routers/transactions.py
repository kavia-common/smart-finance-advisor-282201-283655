from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.db.models import Transaction
from src.db.schemas import Transaction as TransactionSchema
from src.db.schemas import TransactionCreate as TransactionCreateSchema
from src.db.session import get_db

router = APIRouter(prefix="/transactions", tags=["transactions"])


class TransactionUpdate(BaseModel):
    """Schema for updating a transaction (all fields optional)."""
    # Use Optional[...] to avoid PEP 604 union issues in environments where '|' may be problematic.
    txn_date: Optional[date] = Field(None, alias="date", description="Transaction date")
    amount: Optional[float] = Field(None, description="Amount, positive for income")
    category: Optional[str] = Field(None, description="Transaction category")
    description: Optional[str] = Field(None, description="Optional description")
    type: Optional[str] = Field(None, description="Transaction type: expense or income")

    # Keep alias behavior consistent with API (we don't populate by name here)
    model_config = ConfigDict(populate_by_name=False)


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=list[TransactionSchema],
    summary="List transactions",
    description="Retrieve transactions with optional filters by date range and category.",
)
def list_transactions(
    db: Annotated[Session, Depends(get_db)],
    start: Optional[date] = Query(None, description="Start date inclusive (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="End date inclusive (YYYY-MM-DD)"),
    category: Optional[str] = Query(None, description="Filter by category (exact match)"),
) -> list[TransactionSchema]:
    """List transactions with optional filters for date range and category.

    Args:
        db: SQLAlchemy session injected via dependency.
        start: Start date inclusive.
        end: End date inclusive.
        category: Category filter.

    Returns:
        List of transactions sorted by date ascending then id.
    """
    # MVP: single user mode -> user_id = 1
    user_id = 1
    conditions = [Transaction.user_id == user_id]
    if start is not None:
        conditions.append(Transaction.date >= start)
    if end is not None:
        conditions.append(Transaction.date <= end)
    if category is not None:
        conditions.append(Transaction.category == category)

    stmt = select(Transaction).where(and_(*conditions)).order_by(Transaction.date.asc(), Transaction.id.asc())
    result = db.execute(stmt).scalars().all()
    return result


# PUBLIC_INTERFACE
@router.get(
    "/{tx_id}",
    response_model=TransactionSchema,
    summary="Get transaction by id",
    description="Retrieve a single transaction by its ID.",
    responses={404: {"description": "Transaction not found"}},
)
def get_transaction(
    tx_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> TransactionSchema:
    """Get transaction by id for default user.

    Args:
        tx_id: Transaction primary key.
        db: SQLAlchemy session.

    Returns:
        Transaction model serialized.
    """
    tx = db.get(Transaction, tx_id)
    if tx is None or tx.user_id != 1:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=TransactionSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create transaction",
    description="Create a new transaction for the default user.",
)
def create_transaction(
    payload: TransactionCreateSchema,
    db: Annotated[Session, Depends(get_db)],
) -> TransactionSchema:
    """Create a new transaction.

    Args:
        payload: TransactionCreate payload.
        db: SQLAlchemy session.

    Returns:
        Created transaction.
    """
    # MVP single-user
    tx = Transaction(
        user_id=1,
        date=payload.txn_date,  # uses schema attribute; inbound/outbound field remains 'date' via alias
        amount=payload.amount,
        category=payload.category,
        description=payload.description,
        type=payload.type,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


# PUBLIC_INTERFACE
@router.put(
    "/{tx_id}",
    response_model=TransactionSchema,
    summary="Update transaction",
    description="Update an existing transaction by ID.",
    responses={404: {"description": "Transaction not found"}},
)
def update_transaction(
    tx_id: int,
    payload: TransactionUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> TransactionSchema:
    """Update a transaction by id.

    Args:
        tx_id: Transaction primary key.
        payload: Fields to update.
        db: SQLAlchemy session.

    Returns:
        Updated transaction.
    """
    tx = db.get(Transaction, tx_id)
    if tx is None or tx.user_id != 1:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Only update provided fields
    data = payload.model_dump(exclude_unset=True, by_alias=False)
    # Map internal txn_date to ORM 'date' column
    if "txn_date" in data:
        data["date"] = data.pop("txn_date")
    for k, v in data.items():
        setattr(tx, k, v)

    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


# PUBLIC_INTERFACE
@router.delete(
    "/{tx_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete transaction",
    description="Delete a transaction by ID.",
    responses={404: {"description": "Transaction not found"}, 204: {"description": "Deleted"}},
)
def delete_transaction(
    tx_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Delete a transaction.

    Args:
        tx_id: Transaction id.
        db: SQLAlchemy session.

    Returns:
        None
    """
    tx = db.get(Transaction, tx_id)
    if tx is None or tx.user_id != 1:
        raise HTTPException(status_code=404, detail="Transaction not found")

    db.delete(tx)
    db.commit()
    return None
