from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.db.models import Goal, Transaction


@dataclass
class DateRange:
    """Simple date range container (inclusive)."""
    start: date
    end: date


def _today() -> date:
    return date.today()


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _next_month_start(d: date) -> date:
    m = d.month + 1
    y = d.year + (1 if m > 12 else 0)
    m = 1 if m > 12 else m
    return date(y, m, 1)


def _last_30_days_range() -> DateRange:
    end = _today()
    start = end - timedelta(days=29)
    return DateRange(start=start, end=end)


def _fetch_transactions(db: Session, user_id: int, rng: DateRange) -> list[Transaction]:
    stmt = (
        select(Transaction)
        .where(
            and_(
                Transaction.user_id == user_id,
                Transaction.date >= rng.start,
                Transaction.date <= rng.end,
            )
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def _is_income(tx: Transaction) -> bool:
    return (tx.type or "").lower() == "income" or (tx.amount or 0) > 0


def _aggregate_spending_patterns(txs: list[Transaction]) -> tuple[float, Dict[str, float], float]:
    """
    Returns:
        total_income (float),
        per_category_spend (positive amounts),
        avg_daily_spend (based on days covered by txs, fallback 30 days window)
    """
    if not txs:
        return 0.0, {}, 0.0

    first_date = txs[0].date
    last_date = txs[-1].date
    days_span = (last_date - first_date).days + 1
    if days_span <= 0:
        days_span = 1

    total_income = 0.0
    per_cat_spend: Dict[str, float] = defaultdict(float)
    total_spend = 0.0

    for tx in txs:
        amt = float(tx.amount or 0.0)
        if _is_income(tx):
            total_income += amt
        else:
            pos = abs(amt)
            total_spend += pos
            per_cat_spend[tx.category] += pos

    avg_daily_spend = total_spend / float(days_span)
    return total_income, dict(per_cat_spend), avg_daily_spend


# PUBLIC_INTERFACE
def compute_savings_advice(
    db: Session,
    user_id: int,
    period: Optional[str] = None,
) -> dict:
    """Compute savings targets advice based on spending patterns.

    Args:
        db: Session
        user_id: Current user id
        period: "day" | "week" | "month" (default "month")

    Returns:
        {
          "period": "day|week|month",
          "range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
          "current": { "income": float, "expenses": float, "net": float },
          "targets": {
            "daily": float, "weekly": float, "monthly": float
          },
          "category_reductions": [
            {"category": str, "current": float, "suggested_reduction_pct": float, "reduced_amount": float}, ...
          ]
        }
    """
    # Default to last 30 days for behavior baseline
    rng = _last_30_days_range()
    txs = _fetch_transactions(db, user_id, rng)
    income, cat_spend, avg_daily_spend = _aggregate_spending_patterns(txs)
    total_spend = sum(cat_spend.values())
    net = income - total_spend

    # Top categories -> suggest mild reductions (heavier on top categories)
    top = sorted(cat_spend.items(), key=lambda x: x[1], reverse=True)
    reductions = []
    # Heuristic: 10% for top1, 7% for next, 5% for next, 3% for rest of top 5
    pcts = [10.0, 7.0, 5.0, 3.0, 3.0]
    for idx, (cat, amt) in enumerate(top[:5]):
        pct = pcts[idx]
        reduced_amt = round(amt * (pct / 100.0), 2)
        reductions.append(
            {
                "category": cat,
                "current": round(amt, 2),
                "suggested_reduction_pct": pct,
                "reduced_amount": reduced_amt,
            }
        )

    # Compute daily/weekly/monthly targets:
    # Base monthly target: current net + potential reductions total
    reduction_total = sum(item["reduced_amount"] for item in reductions)
    monthly_current_net = net
    monthly_target_net = monthly_current_net + reduction_total
    # Daily target savings: average daily net + portion of reductions over 30 days
    daily_current_net = (income / 30.0) - avg_daily_spend if income > 0 else -avg_daily_spend
    daily_target_net = daily_current_net + (reduction_total / 30.0)
    weekly_target_net = daily_target_net * 7.0

    # Normalize outputs per requested period
    chosen_period = (period or "month").lower()
    if chosen_period not in {"day", "week", "month"}:
        chosen_period = "month"

    targets = {
        "daily": round(daily_target_net, 2),
        "weekly": round(weekly_target_net, 2),
        "monthly": round(monthly_target_net, 2),
    }

    result = {
        "period": chosen_period,
        "range": {"start": rng.start.isoformat(), "end": rng.end.isoformat()},
        "current": {
            "income": round(income, 2),
            "expenses": round(total_spend, 2),
            "net": round(net, 2),
        },
        "targets": targets,
        "category_reductions": reductions,
    }
    return result


# PUBLIC_INTERFACE
def compute_goals_plan(
    db: Session,
    user_id: int,
    today: Optional[date] = None,
) -> dict:
    """Project timelines to goals using current net savings and budgets.

    Strategy:
      - Compute baseline monthly net using last 30 days behavior plus any active monthly budgets
        insight only for context; we primarily use baseline net from last 30 days.
      - For each goal, estimate months to target = max(0, target - current) / max(monthly_net, epsilon)
      - If target_date exists, compute status ("on_track", "ahead", "behind") based on projection.

    Returns:
        {
          "range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
          "baseline": {"monthly_net": float, "avg_daily_spend": float},
          "goals": [
            {
              "id": int, "name": str, "target_amount": float, "current_amount": float,
              "target_date": "YYYY-MM-DD"|None, "remaining": float, "months_to_target": float,
              "projected_completion": "YYYY-MM-DD"|None, "status": "on_track|ahead|behind|no_net"
            }, ...
          ]
        }
    """
    if today is None:
        today = _today()

    # Baseline using last 30 days
    rng = _last_30_days_range()
    txs = _fetch_transactions(db, user_id, rng)
    income, cat_spend, avg_daily_spend = _aggregate_spending_patterns(txs)
    total_spend = sum(cat_spend.values())
    monthly_net = income - total_spend  # use as monthly net approximation

    # Fetch goals
    goals = db.execute(select(Goal).where(Goal.user_id == user_id)).scalars().all()

    # Helper to add months (approximate by stepping to next month starts)
    def add_months(d: date, months: int) -> date:
        res = _month_start(d)
        for _ in range(months):
            res = _next_month_start(res)
        # Return last day approximated as 28th to be safe (uniform month end)
        return date(res.year, res.month, 28)

    epsilon = 1e-6
    results: List[dict] = []
    for g in goals:
        target = float(g.target_amount or 0.0)
        current = float(g.current_amount or 0.0)
        remaining = max(0.0, target - current)

        if monthly_net <= epsilon:
            months_to_target: Optional[float] = None
            projected_completion: Optional[str] = None
            status = "no_net"
        else:
            months_to_target = round(remaining / monthly_net, 2) if remaining > 0 else 0.0
            # Compute projected completion month (round up to next whole month for display)
            whole_months = int(months_to_target) if months_to_target is not None else None
            if months_to_target is not None and months_to_target > 0:
                if abs(months_to_target - int(months_to_target)) > 1e-9:
                    whole_months = int(months_to_target) + 1
            if whole_months is not None:
                proj_date = add_months(today, whole_months)
                projected_completion = proj_date.isoformat()
            else:
                projected_completion = today.isoformat()

            # Determine status vs target_date if provided
            status = "on_track"
            if g.target_date:
                td = g.target_date
                # If we finish before target date -> ahead
                if projected_completion and projected_completion <= date(td.year, td.month, min(td.day, 28)).isoformat():
                    status = "ahead"
                else:
                    status = "behind" if remaining > 0 else "ahead"

        results.append(
            {
                "id": g.id,
                "name": g.name,
                "target_amount": round(target, 2),
                "current_amount": round(current, 2),
                "target_date": g.target_date.isoformat() if g.target_date else None,
                "remaining": round(remaining, 2),
                "months_to_target": months_to_target,
                "projected_completion": projected_completion,
                "status": status,
            }
        )

    return {
        "range": {"start": rng.start.isoformat(), "end": rng.end.isoformat()},
        "baseline": {"monthly_net": round(monthly_net, 2), "avg_daily_spend": round(avg_daily_spend, 2)},
        "goals": results,
    }
