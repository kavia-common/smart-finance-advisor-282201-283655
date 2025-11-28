from datetime import date as DateType, datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


# Base Schemas
class UserBase(BaseModel):
    email: str = Field(..., description="User email")

    # Pydantic v2 configuration (enable ORM mode)
    model_config = ConfigDict(from_attributes=True)


class UserCreate(UserBase):
    pass


class User(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime


class TransactionBase(BaseModel):
    # Avoid name/type clash by using a different attribute name with alias preserved
    txn_date: DateType = Field(..., alias="date", description="Transaction date")
    amount: float = Field(..., description="Amount, positive for income, negative or type determines direction")
    category: str = Field(..., description="Transaction category")
    description: Optional[str] = Field(None, description="Optional description")
    type: str = Field("expense", description="Transaction type: expense or income")

    # Ensure alias usage for both input and output follows API field names
    model_config = ConfigDict(from_attributes=True, populate_by_name=False)


class TransactionCreate(TransactionBase):
    pass


class Transaction(TransactionBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    # Pydantic v2 configuration
    model_config = ConfigDict(from_attributes=True)


class BudgetBase(BaseModel):
    month: str = Field(..., description="Month as YYYY-MM")
    category: str = Field(..., description="Budget category")
    amount: float = Field(..., description="Budgeted amount")

    model_config = ConfigDict(from_attributes=True)


class BudgetCreate(BudgetBase):
    pass


class Budget(BudgetBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    # Pydantic v2 configuration
    model_config = ConfigDict(from_attributes=True)


class GoalBase(BaseModel):
    name: str = Field(..., description="Goal name")
    target_amount: float = Field(..., description="Target amount")
    current_amount: float = Field(0, description="Current saved amount")
    # No clash: field name is 'target_date' (does not equal type 'date')
    target_date: Optional[DateType] = Field(None, description="Optional target date")

    model_config = ConfigDict(from_attributes=True)


class GoalCreate(GoalBase):
    pass


class Goal(GoalBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    # Pydantic v2 configuration
    model_config = ConfigDict(from_attributes=True)
