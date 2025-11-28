from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from src.db.models import Budget, Transaction
from src.db.schemas import Budget as BudgetSchema
from src.db.schemas import BudgetCreate as BudgetCreateSchema
from src.db.session import get_db

router = APIRouter(prefix="/budgets", tags=["budgets"])


class BudgetUpsert(BudgetCreateSchema):
    """
    Payload for creating or updating a budget entry.
    Uses the existing BudgetCreate schema fields (month, category, amount).
    """
    pass


class BudgetQueryParams(BaseModel):
    """Common query param parsing for budgets listing."""
    period: str = Field("month", description="Budget period granularity, currently only 'month' is supported")
    start: str = Field(..., description="Start period, format depends on period. For 'month', use YYYY-MM")

    @field_validator("period")
    @classmethod
    def _validate_period(cls, v: str) -> str:
        allowed = {"month"}
        if v not in allowed:
            raise ValueError(f"Unsupported period: {v}. Allowed: {', '.join(sorted(allowed))}")
        return v

    @field_validator("start")
    @classmethod
    def _validate_start(cls, v: str) -> str:
        # Expect YYYY-MM
        try:
            datetime.strptime(v, "%Y-%m")
        except ValueError as e:
            raise ValueError("start must be in YYYY-MM format") from e
        return v


class BudgetSummaryItem(BaseModel):
    month: str = Field(..., description="Month in YYYY-MM")
    category: str = Field(..., description="Category name")
    budget: float = Field(..., description="Budgeted amount for the month/category")
    spent: float = Field(..., description="Total spent amount (expenses only, positive value)")
    utilization_pct: float = Field(..., description="Spent / Budget * 100 (0 when budget is 0)")


class BudgetSummaryResponse(BaseModel):
    month: str = Field(..., description="Month summarized (YYYY-MM)")
    items: List[BudgetSummaryItem] = Field(default_factory=list, description="Per-category summary list")
    totals: Dict[str, float] = Field(default_factory=dict, description="Overall totals for the month")


def _month_date_range(month_str: str) -> tuple[date, date]:
    """Return first and last date (inclusive) for a month YYYY-MM."""
    dt = datetime.strptime(month_str, "%Y-%m")
    start = date(dt.year, dt.month, 1)
    # Determine next month then subtract one day by clamping to 28 and using >=/< logic
    # For SQLAlchemy filtering we'll use >= start and < next_month_start to avoid month length issues.
    # But this function returns a dummy end equal to the 28th for clarity, unused in filtering.
    end = date(dt.year, dt.month, 28)
    return start, end


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[BudgetSchema],
    summary="List budgets",
    description="List budgets for a given period and start value. Currently supports period=month with start=YYYY-MM.",
)
def list_budgets(
    db: Annotated[Session, Depends(get_db)],
    period: str = Query("month", description="Period granularity, e.g., 'month'"),
    start: str = Query(..., description="Start period, for month use YYYY-MM"),
) -> list[BudgetSchema]:
    """Retrieve budgets for the default user filtered by period.

    Args:
        db: SQLAlchemy session
        period: Currently only 'month'
        start: Month string in YYYY-MM

    Returns:
        List of Budget entries.
    """
    params = BudgetQueryParams(period=period, start=start)
    user_id = 1
    if params.period == "month":
        stmt = (
            select(Budget)
            .where(and_(Budget.user_id == user_id, Budget.month == params.start))
            .order_by(Budget.category.asc(), Budget.id.asc())
        )
        return db.execute(stmt).scalars().all()
    # Should not reach due to validation
    raise HTTPException(status_code=400, detail="Unsupported period")


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=BudgetSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update budget (upsert)",
    description="Create a new budget for a month/category or update existing if found.",
)
def upsert_budget(
    payload: BudgetUpsert,
    db: Annotated[Session, Depends(get_db)],
) -> BudgetSchema:
    """Create or update a budget entry.

    If a budget exists for (user_id, month, category), updates amount. Otherwise creates new.

    Args:
        payload: BudgetUpsert with month YYYY-MM, category, amount
        db: SQLAlchemy session

    Returns:
        The created or updated Budget entry.
    """
    # Validate month format
    try:
        datetime.strptime(payload.month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=422, detail="month must be in YYYY-MM format")

    user_id = 1
    existing = db.execute(
        select(Budget).where(
            and_(Budget.user_id == user_id, Budget.month == payload.month, Budget.category == payload.category)
        )
    ).scalar_one_or_none()

    if existing:
        existing.amount = float(payload.amount)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    b = Budget(
        user_id=user_id,
        month=payload.month,
        category=payload.category,
        amount=float(payload.amount),
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


# PUBLIC_INTERFACE
@router.get(
    "/summary",
    response_model=BudgetSummaryResponse,
    summary="Budget summary for a month",
    description="Returns per-category spent vs budget and utilization percentage for the given month.",
    responses={400: {"description": "Invalid month format"}},
)
def budget_summary(
    db: Annotated[Session, Depends(get_db)],
    month: str = Query(..., description="Target month in YYYY-MM"),
) -> BudgetSummaryResponse:
    """Compute per-category expense totals versus budgets for a given month.

    Notes:
        - Only expense transactions are considered (type='expense').
        - Amounts for expenses are stored as negative in demo data; we convert spent to positive.

    Args:
        db: SQLAlchemy session
        month: Month in YYYY-MM

    Returns:
        BudgetSummaryResponse with items and totals.
    """
    try:
        start_dt = datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be in YYYY-MM format")

    user_id = 1
    month_start = date(start_dt.year, start_dt.month, 1)
    # Next month start
    next_month = start_dt.month + 1 if start_dt.month < 12 else 1
    next_year = start_dt.year + 1 if next_month == 1 else start_dt.year
    next_month_start = date(next_year, next_month, 1)

    # Get budgets for the month
    budgets = db.execute(
        select(Budget).where(and_(Budget.user_id == user_id, Budget.month == month))
    ).scalars().all()

    # Aggregate expenses per category for the month
    spend_rows = db.execute(
        select(
            Transaction.category.label("category"),
            func.sum(Transaction.amount).label("total_amount"),
        ).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.type == "expense",
                Transaction.date >= month_start,
                Transaction.date < next_month_start,
            )
        ).group_by(Transaction.category)
    ).all()

    spent_by_cat: Dict[str, float] = {}
    for row in spend_rows:
        total = float(row.total_amount or 0.0)
        # Expenses are negative in the dataset; convert to positive spent
        spent_by_cat[row.category] = abs(total)

    # Build list combining budgets with any categories that had spending but no budget
    items: list[BudgetSummaryItem] = []
    covered = set()

    for b in budgets:
        spent = spent_by_cat.get(b.category, 0.0)
        budget_amt = float(b.amount or 0.0)
        utilization = (spent / budget_amt * 100.0) if budget_amt > 0 else 0.0
        items.append(
            BudgetSummaryItem(
                month=month,
                category=b.category,
                budget=budget_amt,
                spent=spent,
                utilization_pct=round(utilization, 2),
            )
        )
        covered.add(b.category)

    # Add categories with spend but no budget
    for cat, spent in spent_by_cat.items():
        if cat in covered:
            continue
        items.append(
            BudgetSummaryItem(
                month=month,
                category=cat,
                budget=0.0,
                spent=spent,
                utilization_pct=0.0,
            )
        )

    total_budget = round(sum(i.budget for i in items), 2)
    total_spent = round(sum(i.spent for i in items), 2)
    overall_util = round((total_spent / total_budget * 100.0), 2) if total_budget > 0 else 0.0

    return BudgetSummaryResponse(
        month=month,
        items=sorted(items, key=lambda x: (x.category.lower())),
        totals={
            "budget": total_budget,
            "spent": total_spent,
            "utilization_pct": overall_util,
        },
    )
