from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Literal, Optional, Tuple

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.db.models import Transaction


@dataclass
class DateRange:
    start: date
    end: date  # inclusive


def _coerce_date(d: date | datetime) -> date:
    return d.date() if isinstance(d, datetime) else d


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _next_month_start(d: date) -> date:
    m = d.month + 1
    y = d.year + (1 if m > 12 else 0)
    m = 1 if m > 12 else m
    return date(y, m, 1)


def compute_date_range(
    period: Literal["day", "week", "month"] | None,
    start: Optional[date],
    end: Optional[date],
) -> Tuple[Literal["day", "week", "month"], DateRange]:
    """Compute and normalize the requested date range and default period.

    - If both start and end are missing, default to last 30 days ending today.
    - If only start is provided, end defaults to today.
    - If only end is provided, use end-29 days to end.
    - Period defaults to 'day' when range <= 31 days, else 'month'.
    """
    today = date.today()
    if start is None and end is None:
        end = today
        start = today - timedelta(days=29)
    elif start is None and end is not None:
        end = _coerce_date(end)
        start = end - timedelta(days=29)
    elif start is not None and end is None:
        start = _coerce_date(start)
        end = today
    else:
        start = _coerce_date(start)  # type: ignore[arg-type]
        end = _coerce_date(end)      # type: ignore[arg-type]

    if start > end:
        # swap
        start, end = end, start

    inferred_period: Literal["day", "week", "month"]
    if period in ("day", "week", "month"):
        inferred_period = period  # type: ignore[assignment]
    else:
        delta = (end - start).days
        inferred_period = "day" if delta <= 31 else "month"

    return inferred_period, DateRange(start=start, end=end)


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


# PUBLIC_INTERFACE
def compute_summary(
    db: Session,
    user_id: int,
    period: Optional[Literal["day", "week", "month"]] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict:
    """Compute summary analytics over the requested range, scoped by current_user.id.

    Returns:
      {
        "range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
        "period": "day|week|month",
        "totals": {"income": float, "expenses": float, "net_cash_flow": float},
        "savings_rate": float,  # income>0 ? net/income : 0
        "avg_daily_spend": float,
        "category_breakdown": {"Category": float, ...},  # positive spend values
        "trend": [{"period": "YYYY-MM" or "YYYY-MM-DD" or "YYYY-[W]WW", "income": float, "expenses": float, "net": float}, ...]
      }
    """
    inferred_period, rng = compute_date_range(period, start, end)

    txs = _fetch_transactions(db, user_id, rng)

    total_income = 0.0
    total_expense_abs = 0.0  # positive total of expenses
    days_span = (rng.end - rng.start).days + 1
    # category breakdown for expenses (positive values)
    cat_spend: Dict[str, float] = defaultdict(float)

    # Trend buckets by key -> sums
    trend: Dict[str, Dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expenses": 0.0})

    def bucket_key(d: date) -> str:
        if inferred_period == "day":
            return d.isoformat()
        if inferred_period == "week":
            # ISO week format YYYY-Www
            iso_year, iso_week, _ = d.isocalendar()
            return f"{iso_year}-W{iso_week:02d}"
        # month
        return f"{d.year:04d}-{d.month:02d}"

    for tx in txs:
        amt = float(tx.amount or 0.0)
        d = tx.date
        key = bucket_key(d)

        if _is_income(tx):
            total_income += amt
            trend[key]["income"] += amt
        else:
            # expenses are typically recorded as positive when type='expense'; convert to positive for totals regardless
            exp_pos = abs(amt)
            total_expense_abs += exp_pos
            cat_spend[tx.category] += exp_pos
            trend[key]["expenses"] += exp_pos

    net_cash_flow = total_income - total_expense_abs
    savings_rate = (net_cash_flow / total_income * 100.0) if total_income > 0 else 0.0
    avg_daily_spend = (total_expense_abs / days_span) if days_span > 0 else 0.0

    # Build dense trend series across the period (fill missing buckets with 0s)
    trend_series: List[dict] = []
    if inferred_period == "day":
        cur = rng.start
        while cur <= rng.end:
            k = bucket_key(cur)
            inc = trend[k]["income"]
            exp = trend[k]["expenses"]
            trend_series.append(
                {"period": k, "income": round(inc, 2), "expenses": round(exp, 2), "net": round(inc - exp, 2)}
            )
            cur += timedelta(days=1)
    elif inferred_period == "week":
        # iterate Monday-start weeks across the range
        # find first Monday on/before start
        cur = rng.start - timedelta(days=(rng.start.weekday()))
        while cur <= rng.end:
            k = bucket_key(cur)
            inc = trend[k]["income"]
            exp = trend[k]["expenses"]
            trend_series.append(
                {"period": k, "income": round(inc, 2), "expenses": round(exp, 2), "net": round(inc - exp, 2)}
            )
            cur += timedelta(days=7)
    else:
        # month
        cur = _month_start(rng.start)
        last_month_start = _month_start(rng.end)
        while cur <= last_month_start:
            k = bucket_key(cur)
            inc = trend[k]["income"]
            exp = trend[k]["expenses"]
            trend_series.append(
                {"period": k, "income": round(inc, 2), "expenses": round(exp, 2), "net": round(inc - exp, 2)}
            )
            cur = _next_month_start(cur)

    # Compute category percentage breakdown relative to total expenses (month-wise aggregated is available via trend/filters)
    breakdown_total = sum(cat_spend.values()) or 1.0
    category_breakdown = {k: round(v, 2) for k, v in sorted(cat_spend.items(), key=lambda x: x[0].lower())}
    category_percentages = {k: round((v / breakdown_total) * 100.0, 2) for k, v in category_breakdown.items()}

    result = {
        "range": {"start": rng.start.isoformat(), "end": rng.end.isoformat()},
        "period": inferred_period,
        "totals": {
            "income": round(total_income, 2),
            "expenses": round(total_expense_abs, 2),
            "net_cash_flow": round(net_cash_flow, 2),
        },
        "savings_rate": round(savings_rate, 2),
        "avg_daily_spend": round(avg_daily_spend, 2),
        # Keep raw breakdown as amounts; percentages can be derived client-side or used for insights
        "category_breakdown": category_breakdown,
        "trend": trend_series,
        # not in schema but useful internally; do not expose in API model binding
        "_category_percentages": category_percentages,
    }
    return result


def compute_behaviors(
    db: Session,
    user_id: int,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict:
    """Compute behavioral insights such as top categories, spending streaks, etc.

    For MVP, provide simple insights:
      - top_spending_categories: top 5 by total expense
      - most_expensive_day: date with max total expenses
      - income_days_count: number of days with any income
    """
    _, rng = compute_date_range(None, start, end)
    txs = _fetch_transactions(db, user_id, rng)

    cat_spend: Dict[str, float] = defaultdict(float)
    day_spend: Dict[date, float] = defaultdict(float)
    income_days: set[date] = set()

    for tx in txs:
        amt = float(tx.amount or 0.0)
        d = tx.date
        if _is_income(tx):
            income_days.add(d)
        else:
            exp_pos = abs(amt)
            cat_spend[tx.category] += exp_pos
            day_spend[d] += exp_pos

    top_cats = sorted(cat_spend.items(), key=lambda x: x[1], reverse=True)[:5]
    most_expensive_day = None
    if day_spend:
        d, total = max(day_spend.items(), key=lambda x: x[1])
        most_expensive_day = {"date": d.isoformat(), "total_spent": round(total, 2)}

    return {
        "range": {"start": rng.start.isoformat(), "end": rng.end.isoformat()},
        "top_spending_categories": [{"category": k, "amount": round(v, 2)} for k, v in top_cats],
        "most_expensive_day": most_expensive_day,
        "income_days_count": len(income_days),
    }
