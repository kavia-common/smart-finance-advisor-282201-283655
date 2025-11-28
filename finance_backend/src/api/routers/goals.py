from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Goal
from src.db.schemas import Goal as GoalSchema
from src.db.schemas import GoalCreate as GoalCreateSchema
from src.db.session import get_db

router = APIRouter(prefix="/goals", tags=["goals"])


class GoalUpdate(BaseModel):
    """Schema for updating a goal (all fields optional)."""
    name: Optional[str] = Field(None, description="Goal name")
    target_amount: Optional[float] = Field(None, description="Target amount")
    current_amount: Optional[float] = Field(None, description="Current saved amount")
    target_date: Optional[date] = Field(None, description="Optional target date")


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=list[GoalSchema],
    summary="List goals",
    description="Retrieve all goals for the default user.",
)
def list_goals(
    db: Annotated[Session, Depends(get_db)],
) -> list[GoalSchema]:
    """List all goals for the default user (MVP single-user mode)."""
    user_id = 1
    stmt = (
        select(Goal)
        .where(Goal.user_id == user_id)
        .order_by(Goal.created_at.desc(), Goal.id.desc())
    )
    return db.execute(stmt).scalars().all()


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=GoalSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create goal",
    description="Create a new savings goal for the default user.",
)
def create_goal(
    payload: GoalCreateSchema,
    db: Annotated[Session, Depends(get_db)],
) -> GoalSchema:
    """Create a new goal for the default user."""
    g = Goal(
        user_id=1,
        name=payload.name,
        target_amount=float(payload.target_amount),
        current_amount=float(payload.current_amount or 0),
        target_date=payload.target_date,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


# PUBLIC_INTERFACE
@router.put(
    "/{goal_id}",
    response_model=GoalSchema,
    summary="Update goal",
    description="Update an existing goal by ID for the default user.",
    responses={404: {"description": "Goal not found"}},
)
def update_goal(
    goal_id: int,
    payload: GoalUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> GoalSchema:
    """Update a goal fields that are provided in the payload."""
    g = db.get(Goal, goal_id)
    if g is None or g.user_id != 1:
        raise HTTPException(status_code=404, detail="Goal not found")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(g, k, v)

    db.add(g)
    db.commit()
    db.refresh(g)
    return g


# PUBLIC_INTERFACE
@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete goal",
    description="Delete a goal by ID.",
    responses={404: {"description": "Goal not found"}, 204: {"description": "Deleted"}},
)
def delete_goal(
    goal_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Delete a goal for the default user."""
    g = db.get(Goal, goal_id)
    if g is None or g.user_id != 1:
        raise HTTPException(status_code=404, detail="Goal not found")
    db.delete(g)
    db.commit()
    return None
