from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.db.models import Goal, User
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
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[GoalSchema]:
    """List all goals for the authenticated user."""
    stmt = (
        select(Goal)
        .where(Goal.user_id == current_user.id)
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
    current_user: Annotated[User, Depends(get_current_user)],
) -> GoalSchema:
    """Create a new goal for the authenticated user."""
    g = Goal(
        user_id=current_user.id,
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
    current_user: Annotated[User, Depends(get_current_user)],
) -> GoalSchema:
    """Update a goal fields that are provided in the payload."""
    g = db.get(Goal, goal_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    if g.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

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
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Delete a goal for the authenticated user."""
    g = db.get(Goal, goal_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    if g.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(g)
    db.commit()
    # Explicitly return an empty 204 response (no content)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
