from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.goal import GoalCreate, GoalRead, GoalProgressUpdate, GoalStatusUpdate
from app.services import goal as goal_service

router = APIRouter(prefix="/goals", tags=["Goals"])


@router.post("", response_model=GoalRead, status_code=201)
async def create_goal(
    data: GoalCreate,
    db: AsyncSession = Depends(get_db),
) -> GoalRead:
    """Create a long-term goal with a target date."""
    return await goal_service.create_goal(db, data)


@router.get("", response_model=list[GoalRead])
async def list_goals(
    db: AsyncSession = Depends(get_db),
) -> list[GoalRead]:
    """List all goals, newest first."""
    return await goal_service.list_goals(db)


@router.patch("/{goal_id}/progress", response_model=GoalRead)
async def update_progress(
    goal_id: int,
    data: GoalProgressUpdate,
    db: AsyncSession = Depends(get_db),
) -> GoalRead:
    """Update goal progress (0–100). Auto-completes at 100."""
    goal = await goal_service.update_goal_progress(db, goal_id, data)
    if goal is None:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found")
    return goal


@router.patch("/{goal_id}/status", response_model=GoalRead)
async def update_status(
    goal_id: int,
    data: GoalStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> GoalRead:
    """Update goal status (active|completed|paused|abandoned)."""
    goal = await goal_service.update_goal_status(db, goal_id, data)
    if goal is None:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found")
    return goal
