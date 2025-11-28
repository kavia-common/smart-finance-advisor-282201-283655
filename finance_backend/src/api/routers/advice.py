from __future__ import annotations

from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.services.advice_service import compute_goals_plan, compute_savings_advice

router = APIRouter(prefix="/advice", tags=["advice"])


class SavingsTargetAmounts(BaseModel):
    daily: float = Field(..., description="Target daily net savings")
    weekly: float = Field(..., description="Target weekly net savings")
    monthly: float = Field(..., description="Target monthly net savings")


class SavingsCategoryReduction(BaseModel):
    category: str = Field(..., description="Category name")
    current: float = Field(..., description="Current spend in the category over the analysis window")
    suggested_reduction_pct: float = Field(..., description="Suggested reduction percent for this category")
    reduced_amount: float = Field(..., description="Amount to reduce for this category")


class SavingsAdviceResponse(BaseModel):
    period: str = Field(..., description="Requested aggregation focus period")
    range: Dict[str, str] = Field(..., description="Start/end dates used for the analysis")
    current: Dict[str, float] = Field(..., description="Current totals: income, expenses, net")
    targets: SavingsTargetAmounts = Field(..., description="Savings targets by period")
    category_reductions: List[SavingsCategoryReduction] = Field(
        default_factory=list, description="Suggested reductions for top categories"
    )


class GoalPlanItem(BaseModel):
    id: int
    name: str
    target_amount: float
    current_amount: float
    target_date: Optional[str] = Field(None, description="Goal target date (YYYY-MM-DD) if provided")
    remaining: float
    months_to_target: Optional[float] = Field(
        None, description="Months to reach target based on current baseline monthly net (None when non-positive net)"
    )
    projected_completion: Optional[str] = Field(
        None, description="Projected completion date (YYYY-MM-DD) if computable"
    )
    status: str = Field(..., description="on_track | ahead | behind | no_net")


class GoalsPlanResponse(BaseModel):
    range: Dict[str, str] = Field(..., description="Start/end for baseline window")
    baseline: Dict[str, float] = Field(..., description="Baseline stats such as monthly_net and avg_daily_spend")
    goals: List[GoalPlanItem] = Field(default_factory=list, description="Goals with projections")


# PUBLIC_INTERFACE
@router.get(
    "/savings",
    response_model=SavingsAdviceResponse,
    summary="Savings targets advice",
    description=(
        "Compute savings targets based on recent spending patterns. "
        "Suggest category reductions and provide daily/weekly/monthly savings targets."
    ),
    responses={200: {"description": "Advice computed"}},
)
def advice_savings(
    db: Annotated[Session, Depends(get_db)],
    period: Optional[str] = Query(
        "month",
        description="Target period for focus of the response: day | week | month",
    ),
) -> SavingsAdviceResponse:
    """Provide savings advice including reduction suggestions and net targets."""
    user_id = 1
    data = compute_savings_advice(db, user_id=user_id, period=period)
    return SavingsAdviceResponse(
        period=data["period"],
        range=data["range"],
        current=data["current"],
        targets=SavingsTargetAmounts(**data["targets"]),
        category_reductions=[SavingsCategoryReduction(**c) for c in data["category_reductions"]],
    )


# PUBLIC_INTERFACE
@router.get(
    "/goals-plan",
    response_model=GoalsPlanResponse,
    summary="Goals plan projections",
    description=(
        "Project timelines for goals using current net savings baseline. "
        "Indicates months to target and projected completion date."
    ),
    responses={200: {"description": "Plan computed"}},
)
def advice_goals_plan(
    db: Annotated[Session, Depends(get_db)],
) -> GoalsPlanResponse:
    """Provide goals projection plan based on recent savings baseline."""
    user_id = 1
    data = compute_goals_plan(db, user_id=user_id)
    return GoalsPlanResponse(
        range=data["range"],
        baseline=data["baseline"],
        goals=[GoalPlanItem(**g) for g in data["goals"]],
    )
