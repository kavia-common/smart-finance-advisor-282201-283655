from __future__ import annotations

from datetime import date
from typing import Annotated, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.services.analytics_service import compute_behaviors, compute_summary

router = APIRouter(prefix="/analytics", tags=["analytics"])


class TrendPoint(BaseModel):
    period: str = Field(..., description="Time bucket label (YYYY-MM, YYYY-MM-DD, or ISO week 'YYYY-Www')")
    income: float = Field(..., description="Total income in this period")
    expenses: float = Field(..., description="Total expenses (positive) in this period")
    net: float = Field(..., description="Net income - expenses for this period")


class AnalyticsTotals(BaseModel):
    income: float = Field(..., description="Total income over the range")
    expenses: float = Field(..., description="Total expenses (positive) over the range")
    net_cash_flow: float = Field(..., description="Income minus expenses over the range")


class AnalyticsSummaryResponse(BaseModel):
    range: Dict[str, str] = Field(..., description="Start/end date in ISO")
    period: Literal["day", "week", "month"] = Field(..., description="Aggregation period used")
    totals: AnalyticsTotals
    savings_rate: float = Field(..., description="Net / Income * 100, 0 when income is 0")
    avg_daily_spend: float = Field(..., description="Average daily spending across the date range")
    category_breakdown: Dict[str, float] = Field(default_factory=dict, description="Per-category spent totals")
    trend: List[TrendPoint] = Field(default_factory=list, description="Time series over the requested period")


class AnalyticsBehaviorCategory(BaseModel):
    category: str = Field(..., description="Category name")
    amount: float = Field(..., description="Total spent in category")


class AnalyticsBehaviorsResponse(BaseModel):
    range: Dict[str, str] = Field(..., description="Start/end date in ISO")
    top_spending_categories: List[AnalyticsBehaviorCategory] = Field(default_factory=list, description="Top spending categories")
    most_expensive_day: Optional[Dict[str, float | str]] = Field(
        None, description="Object with 'date' and 'total_spent' for the costliest day"
    )
    income_days_count: int = Field(..., description="Number of days having any income recorded")


# PUBLIC_INTERFACE
@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    summary="Analytics summary",
    description="Compute totals, savings rate, average daily spend, category breakdown, and trend series over a requested period and date range.",
    responses={
        200: {"description": "Summary computed"},
        422: {"description": "Validation Error"},
    },
)
def analytics_summary(
    db: Annotated[Session, Depends(get_db)],
    period: Optional[Literal["day", "week", "month"]] = Query(None, description="Aggregation period; defaults based on range size"),
    start: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
) -> AnalyticsSummaryResponse:
    """Return financial analytics summary for the default user (MVP single-user mode).

    Args:
        db: SQLAlchemy session dependency.
        period: Aggregation period - day/week/month. If omitted, inferred from range length.
        start: Start date inclusive (YYYY-MM-DD). If omitted, defaults to last 30 days.
        end: End date inclusive (YYYY-MM-DD). If omitted, defaults to today.

    Returns:
        AnalyticsSummaryResponse payload with totals, savings rate, avg daily spend, category breakdown, and trend.
    """
    user_id = 1
    data = compute_summary(db, user_id=user_id, period=period, start=start, end=end)
    return AnalyticsSummaryResponse(
        range=data["range"],
        period=data["period"],
        totals=AnalyticsTotals(**data["totals"]),
        savings_rate=data["savings_rate"],
        avg_daily_spend=data["avg_daily_spend"],
        category_breakdown=data["category_breakdown"],
        trend=[TrendPoint(**tp) for tp in data["trend"]],
    )


# PUBLIC_INTERFACE
@router.get(
    "/behaviors",
    response_model=AnalyticsBehaviorsResponse,
    summary="Analytics behaviors",
    description="Provide behavior insights like top spending categories and most expensive day within an optional date range.",
    responses={
        200: {"description": "Behaviors computed"},
        422: {"description": "Validation Error"},
    },
)
def analytics_behaviors(
    db: Annotated[Session, Depends(get_db)],
    start: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
) -> AnalyticsBehaviorsResponse:
    """Return behavioral analytics for the default user.

    Args:
        db: SQLAlchemy session dependency.
        start: Optional start date inclusive.
        end: Optional end date inclusive.

    Returns:
        AnalyticsBehaviorsResponse payload with insights.
    """
    user_id = 1
    data = compute_behaviors(db, user_id=user_id, start=start, end=end)
    return AnalyticsBehaviorsResponse(
        range=data["range"],
        top_spending_categories=[AnalyticsBehaviorCategory(**c) for c in data["top_spending_categories"]],
        most_expensive_day=data["most_expensive_day"],
        income_days_count=data["income_days_count"],
    )
