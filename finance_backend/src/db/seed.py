from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Iterable

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from src.db.models import Transaction, User

# Categories leveraging common personal finance domains
EXPENSE_CATEGORIES = [
    # Essentials
    "Rent/Mortgage",
    "Utilities",
    "Groceries",
    "Transportation",
    "Healthcare",
    "Insurance",
    # Discretionary
    "Dining",
    "Entertainment",
    "Shopping",
    "Travel",
    "Subscriptions",
    "Education",
    # Misc
    "Gifts/Donations",
    "Fees",
]

INCOME_CATEGORIES = ["Salary", "Bonus", "Investment", "Refund"]

# PUBLIC_INTERFACE
def ensure_default_user(db: Session) -> User:
    """Ensure there is a default demo user with id=1.

    Returns:
        The ensured or created User instance.

    Notes:
        This function tolerates databases that were created before migrations
        added the `password_hash` column to `users`. It detects existing
        columns and inserts/selects accordingly to avoid OperationalError.
    """
    # Fast path: by primary key
    existing = db.get(User, 1)
    if existing:
        return existing

    # Fallback: look up by email via ORM (safe regardless of password_hash presence)
    existing_by_email = db.execute(select(User).where(User.email == "demo@user")).scalar_one_or_none()
    if existing_by_email:
        return existing_by_email

    # Introspect columns to see if password_hash exists on the physical table
    has_pwd_col = False
    try:
        # SQLite PRAGMA (rows: cid, name, type, notnull, dflt_value, pk)
        rows = list(db.execute(text("PRAGMA table_info(users)")))
        cols = [str(r[1]).lower() for r in rows]
        has_pwd_col = "password_hash" in cols
    except Exception:
        # Try generic information_schema (Postgres/others)
        try:
            rows2 = list(
                db.execute(
                    text(
                        "SELECT LOWER(column_name) FROM information_schema.columns WHERE LOWER(table_name)='users'"
                    )
                )
            )
            cols2 = [str(r[0]).lower() for r in rows2]
            has_pwd_col = "password_hash" in cols2
        except Exception:
            # Assume exists; errors will be handled by retrying minimal insert
            has_pwd_col = True

    # Attempt safe creation based on detected columns
    try:
        # Create via ORM; if column missing in DB, DB will raise and we'll retry minimal insert
        if has_pwd_col:
            user = User(id=1, email="demo@user", password_hash=None)
        else:
            user = User(id=1, email="demo@user")  # omit password_hash attribute
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except Exception:
        db.rollback()
        # Minimal column insert via raw SQL that works when password_hash is missing
        try:
            db.execute(text("INSERT INTO users (id, email) VALUES (:id, :email)"), {"id": 1, "email": "demo@user"})
            db.commit()
            user = db.get(User, 1)
            if user:
                return user
        except Exception:
            db.rollback()
            # If above failed (e.g., password_hash exists and is required), try including it explicitly
            try:
                db.execute(
                    text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :ph)"),
                    {"id": 1, "email": "demo@user", "ph": None},
                )
                db.commit()
                user = db.get(User, 1)
                if user:
                    return user
            except Exception:
                db.rollback()
                # Final attempt: select in case of race creation elsewhere
                fallback = db.execute(select(User).where(User.email == "demo@user")).scalar_one_or_none()
                if fallback:
                    return fallback
                raise


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _daterange(days_back: int) -> Iterable[date]:
    today = date.today()
    for i in range(days_back, -1, -1):
        yield today - timedelta(days=i)


def _random_desc(category: str) -> str:
    samples = {
        "Groceries": ["SuperMart", "Fresh Foods", "Local Market", "GreenGrocer"],
        "Dining": ["Bistro Cafe", "Pizza Place", "Sushi Bar", "Steak House"],
        "Transportation": ["Gas Station", "Ride-share", "Metro Card", "Parking"],
        "Subscriptions": ["StreamFlix", "Music+","News Premium","Cloud Storage"],
        "Entertainment": ["Cinema", "Concert", "eBooks", "Gaming"],
        "Shopping": ["Online Store", "Department Store", "Electronics"],
        "Travel": ["Airline", "Hotel", "Car Rental", "Travel Agent"],
        "Rent/Mortgage": ["Monthly rent", "Mortgage payment"],
        "Utilities": ["Electricity", "Water", "Internet", "Mobile"],
        "Healthcare": ["Pharmacy", "Clinic", "Dental"],
        "Insurance": ["Auto Insurance", "Home Insurance", "Health Insurance"],
        "Education": ["Online Course", "Books", "Workshop"],
        "Gifts/Donations": ["Charity", "Birthday Gift", "Holiday Gift"],
        "Fees": ["Bank Fee", "ATM Fee", "Service Charge"],
        "Salary": ["Monthly Salary"],
        "Bonus": ["Quarterly Bonus"],
        "Investment": ["Dividend", "Capital Gains"],
        "Refund": ["Store Refund", "Tax Refund"],
    }
    cands = samples.get(category, [category])
    return random.choice(cands)


def _generate_recurring_expenses(base_day: int = 1) -> list[dict]:
    """Define recurring monthly expenses patterns."""
    patterns = [
        {"category": "Rent/Mortgage", "amount": 1500.00, "day": base_day},
        {"category": "Utilities", "amount": 120.00, "day": base_day + 4},
        {"category": "Subscriptions", "amount": 19.99, "day": base_day + 8},
        {"category": "Insurance", "amount": 85.00, "day": base_day + 12},
        {"category": "Mobile", "amount": 65.00, "day": base_day + 16},  # falls under Utilities desc 'Mobile'
    ]
    return patterns


def _apply_recurring_for_month(month_start: date) -> list[dict]:
    """Create expense entries for recurring patterns for a given month."""
    entries: list[dict] = []
    for p in _generate_recurring_expenses():
        # Clamp day within the month (simple approach for demo data)
        d = min(28, p["day"])  # keep within 1..28 to avoid month length issues
        tx_date = date(month_start.year, month_start.month, d)
        cat = p["category"] if p["category"] != "Mobile" else "Utilities"
        entries.append(
            {
                "date": tx_date,
                "amount": float(-abs(p["amount"])),
                "category": cat,
                "description": f"Recurring: {_random_desc(cat)}",
                "type": "expense",
            }
        )
    return entries


def _random_expense_for_date(dt: date) -> dict:
    category = random.choice(EXPENSE_CATEGORIES)
    base = {
        "Rent/Mortgage": (1200, 2000),
        "Utilities": (50, 200),
        "Groceries": (20, 150),
        "Transportation": (5, 80),
        "Healthcare": (10, 150),
        "Insurance": (40, 120),
        "Dining": (8, 60),
        "Entertainment": (5, 120),
        "Shopping": (10, 250),
        "Travel": (30, 400),
        "Subscriptions": (5, 30),
        "Education": (10, 150),
        "Gifts/Donations": (5, 120),
        "Fees": (1, 25),
    }
    lo, hi = base.get(category, (5, 100))
    amount = round(random.uniform(lo, hi), 2)
    return {
        "date": dt,
        "amount": float(-abs(amount)),
        "category": category,
        "description": _random_desc(category),
        "type": "expense",
    }


def _random_income_for_month(month_start: date) -> list[dict]:
    """Generate 1-2 income entries per month (salary + occasional bonus/dividend)."""
    entries: list[dict] = []
    # Salary on the last business week of the month (approximate: day 25-28)
    salary_day = min(28, 25 + random.randint(0, 3))
    salary_date = date(month_start.year, month_start.month, salary_day)
    entries.append(
        {
            "date": salary_date,
            "amount": float(round(random.uniform(3000, 6000), 2)),
            "category": "Salary",
            "description": _random_desc("Salary"),
            "type": "income",
        }
    )
    # Occasional second income
    if random.random() < 0.35:
        alt_cat = random.choice(["Bonus", "Investment", "Refund"])
        alt_day = min(28, random.randint(10, 22))
        alt_date = date(month_start.year, month_start.month, alt_day)
        entries.append(
            {
                "date": alt_date,
                "amount": float(round(random.uniform(100, 1200), 2)),
                "category": alt_cat,
                "description": _random_desc(alt_cat),
                "type": "income",
            }
        )
    return entries


def _count_transactions(db: Session, user_id: int) -> int:
    return db.execute(select(func.count()).select_from(Transaction).where(Transaction.user_id == user_id)).scalar_one() or 0


# PUBLIC_INTERFACE
def clear_demo_data(db: Session) -> int:
    """Delete all transactions for the demo user (idempotent).

    Returns:
        Number of deleted transactions.
    """
    user = ensure_default_user(db)
    stmt = delete(Transaction).where(Transaction.user_id == user.id)
    result = db.execute(stmt)
    db.commit()
    return int(result.rowcount or 0)


# PUBLIC_INTERFACE
def load_demo_data(
    db: Session,
    months_back: int = 6,
    approx_total: int = 500,
    random_seed: int | None = 42,
) -> dict:
    """Populate the database with demo transactions for the last N months.

    The generator creates:
      - Recurring monthly expenses
      - Random daily expenses
      - 1-2 income entries per month

    Args:
        db: Active SQLAlchemy session
        months_back: Number of months to generate backwards from current month (inclusive of current month)
        approx_total: Target number of total transactions (best effort)
        random_seed: Optional seed for deterministic generation (use None for non-deterministic)

    Returns:
        Summary dict with counts and range.
    """
    if random_seed is not None:
        random.seed(random_seed)

    user = ensure_default_user(db)

    # Decide total days to cover to approximate requested total
    # We'll spread daily random expenses then add recurring + income.
    today = date.today()
    month_starts: list[date] = []
    cur = date(today.year, today.month, 1)
    for _ in range(months_back):
        month_starts.append(cur)
        # move to previous month
        prev_month = cur.month - 1 or 12
        prev_year = cur.year - 1 if prev_month == 12 else cur.year
        cur = date(prev_year, prev_month, 1)

    # Ensure unique and sorted ascending by date
    month_starts = sorted(set(month_starts))

    # Estimate daily random expense count to hit approx_total
    # For each month we also add recurring (~5) and income (~1.35 average).
    # spread across days: use roughly 1-4 random daily expenses per day
    # pick how many days we will use (e.g., 20 days per month)
    entries: list[Transaction] = []

    for mstart in month_starts:
        # Recurring
        for rec in _apply_recurring_for_month(mstart):
            entries.append(
                Transaction(
                    user_id=user.id,
                    date=rec["date"],
                    amount=rec["amount"],
                    category=rec["category"],
                    description=rec["description"],
                    type=rec["type"],
                )
            )

        # Income
        for inc in _random_income_for_month(mstart):
            entries.append(
                Transaction(
                    user_id=user.id,
                    date=inc["date"],
                    amount=inc["amount"],
                    category=inc["category"],
                    description=inc["description"],
                    type=inc["type"],
                )
            )

        # Daily random expenses: choose a subset of days in the month
        # pick about 18-24 days in the month with random counts
        days_in_month = 28  # keep safe bound for demo simplicity
        days_used = sorted(random.sample(range(1, days_in_month + 1), k=random.randint(18, 24)))
        for day in days_used:
            dt = date(mstart.year, mstart.month, day)
            # 1-3 expenses for the day
            for _ in range(random.randint(1, 3)):
                exp = _random_expense_for_date(dt)
                entries.append(
                    Transaction(
                        user_id=user.id,
                        date=exp["date"],
                        amount=exp["amount"],
                        category=exp["category"],
                        description=exp["description"],
                        type=exp["type"],
                    )
                )

    # If we overshot the approx_total significantly, randomly trim extras while preserving chronological spread
    if len(entries) > approx_total + 100:
        # Keep recurring and income first, then sample the rest
        recurring_income = [e for e in entries if e.type == "income" or "Recurring:" in (e.description or "")]
        variable_expenses = [e for e in entries if e not in recurring_income]
        keep_needed = max(0, approx_total - len(recurring_income))
        variable_keep = random.sample(variable_expenses, k=min(keep_needed, len(variable_expenses)))
        entries = sorted(recurring_income + variable_keep, key=lambda x: x.date)

    # Clear existing demo transactions to make seeding idempotent and safe to re-run
    clear_demo_data(db)

    # Bulk save
    db.add_all(entries)
    db.commit()

    # Simple summary
    first_date = min((t.date for t in entries), default=None)
    last_date = max((t.date for t in entries), default=None)
    total = _count_transactions(db, user.id)
    return {
        "user_id": user.id,
        "inserted": len(entries),
        "total_transactions": total,
        "from": first_date.isoformat() if first_date else None,
        "to": last_date.isoformat() if last_date else None,
        "months": len(month_starts),
    }
