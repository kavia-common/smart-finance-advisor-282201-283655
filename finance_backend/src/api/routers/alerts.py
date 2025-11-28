from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.db.models import Budget, Transaction, User
from src.db.session import get_db

router = APIRouter(prefix="/alerts", tags=["alerts"])


class OverspendingItem(BaseModel):
    """Alert item describing utilization relative to budget."""
    month: str = Field(..., description="Month in YYYY-MM")
    category: str = Field(..., description="Category name")
    budget: float = Field(..., description="Budgeted amount for the month/category")
    spent: float = Field(..., description="Total spent amount (expenses only, positive value)")
    utilization_pct: float = Field(..., description="Spent / Budget * 100 (0 when budget is 0)")
    severity: str = Field(..., description="Severity level: normal | warning | critical")


class OverspendingResponse(BaseModel):
    """Response model for overspending alerts."""
    month: str = Field(..., description="Month evaluated (YYYY-MM)")
    items: List[OverspendingItem] = Field(default_factory=list, description="Per-category overspending alerts")


def _parse_month(month: str) -> date:
    """Parse YYYY-MM to first day date."""
    try:
        dt = datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be in YYYY-MM format")
    return date(dt.year, dt.month, 1)


def _next_month_start(d: date) -> date:
    m = d.month + 1
    y = d.year + (1 if m > 12 else 0)
    m = 1 if m > 12 else m
    return date(y, m, 1)


def _severity(utilization_pct: float) -> str:
    """
    Map utilization percentage to severity:
      - critical: >= 100%
      - warning: >= 90% and < 100%
      - normal: < 90%
    """
    if utilization_pct >= 100.0:
        return "critical"
    if utilization_pct >= 90.0:
        return "warning"
    return "normal"


# PUBLIC_INTERFACE
@router.get(
    "/overspending",
    response_model=OverspendingResponse,
    summary="Overspending alerts for a month",
    description=(
        "Compute per-category spent vs budget for the given month and return utilization and severity.\n"
        "Severity rules: critical (>=100%), warning (>=90% and <100%), normal (<90%). "
        "Categories without a budget are treated as budget=0 and result in utilization 0 and normal severity."
    ),
    responses={
        200: {"description": "Alerts computed"},
        400: {"description": "Invalid month format"},
    },
)
def overspending_alerts(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    month: str = Query(..., description="Target month in YYYY-MM"),
) -> OverspendingResponse:
    """Compute overspending alerts for the default user in MVP single-user mode.

    Args:
        db: SQLAlchemy session dependency.
        month: Month in YYYY-MM format.

    Returns:
        OverspendingResponse containing items with budget, spent, utilization percentage and severity per category.
    """
    user_id = current_user.id
    month_start = _parse_month(month)
    next_month_start = _next_month_start(month_start)

    # Fetch budgets for the month
    budgets = db.execute(
        select(Budget).where(and_(Budget.user_id == user_id, Budget.month == month))
    ).scalars().all()

    # Aggregate expenses per category for the month (positive spent)
    spend_rows = db.execute(
        select(
            Transaction.category.label("category"),
            func.sum(Transaction.amount).label("total_amount"),
        )
        .where(
            and_(
                Transaction.user_id == user_id,
                Transaction.type == "expense",
                Transaction.date >= month_start,
                Transaction.date < next_month_start,
            )
        )
        .group_by(Transaction.category)
    ).all()

    spent_by_cat: Dict[str, float] = {}
    for row in spend_rows:
        total = float(row.total_amount or 0.0)
        spent_by_cat[row.category] = abs(total)

    # Combine budgets and spending; include categories without a budget as budget=0
    items: List[OverspendingItem] = []
    covered = set()

    for b in budgets:
        budget_amt = float(b.amount or 0.0)
        spent = spent_by_cat.get(b.category, 0.0)
        util = (spent / budget_amt * 100.0) if budget_amt > 0 else 0.0
        items.append(
            OverspendingItem(
                month=month,
                category=b.category,
                budget=round(budget_amt, 2),
                spent=round(spent, 2),
                utilization_pct=round(util, 2),
                severity=_severity(util),
            )
        )
        covered.add(b.category)

    # Add categories with spend but no budget
    for cat, spent in spent_by_cat.items():
        if cat in covered:
            continue
        items.append(
            OverspendingItem(
                month=month,
                category=cat,
                budget=0.0,
                spent=round(spent, 2),
                utilization_pct=0.0,
                severity="normal",
            )
        )

    # Sort by highest utilization then by category
    items.sort(key=lambda x: (-x.utilization_pct, x.category.lower()))

    return OverspendingResponse(month=month, items=items)
