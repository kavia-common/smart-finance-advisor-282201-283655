from datetime import date as DateType, datetime

from pydantic import BaseModel, Field, ConfigDict


# Base Schemas
class UserBase(BaseModel):
    email: str = Field(..., description="User email")


class UserCreate(UserBase):
    pass


class User(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    # Pydantic v2 configuration
    model_config = ConfigDict(from_attributes=True)


class TransactionBase(BaseModel):
    date: DateType = Field(..., description="Transaction date")
    amount: float = Field(..., description="Amount, positive for income, negative or type determines direction")
    category: str = Field(..., description="Transaction category")
    description: str | None = Field(None, description="Optional description")
    type: str = Field("expense", description="Transaction type: expense or income")


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
    target_date: DateType | None = Field(None, description="Optional target date")


class GoalCreate(GoalBase):
    pass


class Goal(GoalBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    # Pydantic v2 configuration
    model_config = ConfigDict(from_attributes=True)
