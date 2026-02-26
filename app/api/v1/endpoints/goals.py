from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.goal import GoalCreate, GoalProgressUpdate, GoalRead, GoalStatusUpdate
from app.services import goal as goal_service

router = APIRouter(prefix="/goals", tags=["Goals"])


@router.post("", response_model=GoalRead, status_code=201)
async def create_goal(
    data: GoalCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> GoalRead:
    """Create a long-term goal with a target date."""
    goal = await goal_service.create_goal(db, data, organization_id=actor["org_id"])
    await record_action(
        db,
        event_type="goal_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="goal",
        entity_id=goal.id,
        payload_json={"title": data.title},
    )
    return goal


@router.get("", response_model=list[GoalRead])
async def list_goals(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[GoalRead]:
    """List all goals, newest first."""
    return await goal_service.list_goals(db, organization_id=actor["org_id"], limit=limit)


@router.patch("/{goal_id}/progress", response_model=GoalRead)
async def update_progress(
    goal_id: int,
    data: GoalProgressUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> GoalRead:
    """Update goal progress (0-100). Auto-completes at 100."""
    goal = await goal_service.update_goal_progress(db, goal_id, data, organization_id=actor["org_id"])
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.patch("/{goal_id}/status", response_model=GoalRead)
async def update_status(
    goal_id: int,
    data: GoalStatusUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> GoalRead:
    """Update goal status (active|completed|paused|abandoned)."""
    goal = await goal_service.update_goal_status(db, goal_id, data, organization_id=actor["org_id"])
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal
