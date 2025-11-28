from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base


class TimestampMixin:
    """Mixin for created/updated timestamps."""
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class User(Base, TimestampMixin):
    """User model supporting multi-user; MVP seeds a default demo user with id=1."""
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_email", "email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="demo@user")
    # Store a hashed password; nullable for demo user
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)

    # Relationships
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    budgets: Mapped[list["Budget"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    goals: Mapped[list["Goal"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Transaction(Base, TimestampMixin):
    """Financial transaction records."""
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_date", "user_id", "date"),
        Index("ix_transactions_user_category", "user_id", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="expense")  # expense | income

    user: Mapped["User"] = relationship(back_populates="transactions")


class Budget(Base, TimestampMixin):
    """Monthly budget by category."""
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "month", "category", name="uq_budgets_user_month_category"),
        Index("ix_budgets_user_month", "user_id", "month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # YYYY-MM
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    user: Mapped["User"] = relationship(back_populates="budgets")


class Goal(Base, TimestampMixin):
    """Savings goals."""
    __tablename__ = "goals"
    __table_args__ = (
        Index("ix_goals_user", "user_id"),
        Index("ix_goals_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    target_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    current_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, default=None)

    user: Mapped["User"] = relationship(back_populates="goals")
