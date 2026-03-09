from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_workspace_id, get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.goal import GoalCreate, GoalProgressUpdate, GoalRead, GoalStatusUpdate
from app.schemas.project import ProjectRead
from app.services import goal as goal_service
from app.services import key_result as kr_service
from app.services import project as project_service


class KeyResultCreate(BaseModel):
    title: str = Field(..., max_length=500)
    description: str | None = None
    metric_unit: str | None = Field(None, max_length=50)
    target_value: float = 100.0
    current_value: float = 0.0


class KeyResultUpdate(BaseModel):
    title: str | None = Field(None, max_length=500)
    current_value: float | None = None
    status: str | None = Field(None, pattern=r"^(active|completed|abandoned)$")


class KeyResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    goal_id: int
    title: str
    description: str | None = None
    metric_unit: str | None = None
    target_value: float
    current_value: float
    progress: int
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

router = APIRouter(prefix="/goals", tags=["Goals"])


@router.post("", response_model=GoalRead, status_code=201)
async def create_goal(
    data: GoalCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    workspace_id: int = Depends(get_current_workspace_id),
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
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> list[GoalRead]:
    """List all goals, newest first."""
    return await goal_service.list_goals(db, organization_id=actor["org_id"], limit=limit, offset=offset)


@router.patch("/{goal_id}/progress", response_model=GoalRead)
async def update_progress(
    goal_id: int,
    data: GoalProgressUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    workspace_id: int = Depends(get_current_workspace_id),
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
    workspace_id: int = Depends(get_current_workspace_id),
) -> GoalRead:
    """Update goal status (active|completed|paused|abandoned)."""
    goal = await goal_service.update_goal_status(db, goal_id, data, organization_id=actor["org_id"])
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.get("/{goal_id}/key-results", response_model=list[KeyResultRead])
async def list_key_results(
    goal_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> list[KeyResultRead]:
    """List key results for a goal (OKR)."""
    goal = await goal_service.get_goal(db, goal_id, organization_id=actor["org_id"])
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    items = await kr_service.list_key_results(db, organization_id=actor["org_id"], goal_id=goal_id)
    return [KeyResultRead.model_validate(kr, from_attributes=True) for kr in items]


@router.post("/{goal_id}/key-results", response_model=KeyResultRead, status_code=201)
async def create_key_result(
    goal_id: int,
    data: KeyResultCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> KeyResultRead:
    """Add a measurable key result to a goal."""
    goal = await goal_service.get_goal(db, goal_id, organization_id=actor["org_id"])
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    kr = await kr_service.create_key_result(
        db, organization_id=actor["org_id"], goal_id=goal_id,
        title=data.title, description=data.description,
        metric_unit=data.metric_unit, target_value=data.target_value,
        current_value=data.current_value,
    )
    # Recalculate goal progress from KRs
    new_progress = await kr_service.recalculate_goal_progress(db, actor["org_id"], goal_id)
    from app.schemas.goal import GoalProgressUpdate as _GPU
    await goal_service.update_goal_progress(db, goal_id, _GPU(progress=new_progress), organization_id=actor["org_id"])
    await record_action(
        db, event_type="key_result_created", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="key_result", entity_id=kr.id,
        payload_json={"goal_id": goal_id, "title": data.title},
    )
    return KeyResultRead.model_validate(kr, from_attributes=True)


@router.patch("/{goal_id}/key-results/{kr_id}", response_model=KeyResultRead)
async def update_key_result(
    goal_id: int,
    kr_id: int,
    data: KeyResultUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> KeyResultRead:
    """Update a key result's current value or status."""
    kr = await kr_service.update_key_result(
        db, organization_id=actor["org_id"], kr_id=kr_id,
        current_value=data.current_value, title=data.title, status=data.status,
    )
    if kr is None:
        raise HTTPException(status_code=404, detail="Key result not found")
    # Recalculate goal progress from KRs
    new_progress = await kr_service.recalculate_goal_progress(db, actor["org_id"], goal_id)
    from app.schemas.goal import GoalProgressUpdate as _GPU
    await goal_service.update_goal_progress(db, goal_id, _GPU(progress=new_progress), organization_id=actor["org_id"])
    return KeyResultRead.model_validate(kr, from_attributes=True)


@router.delete("/{goal_id}/key-results/{kr_id}", status_code=204)
async def delete_key_result(
    goal_id: int,
    kr_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> None:
    deleted = await kr_service.delete_key_result(db, organization_id=actor["org_id"], kr_id=kr_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Key result not found")
    # Recalculate goal progress
    new_progress = await kr_service.recalculate_goal_progress(db, actor["org_id"], goal_id)
    from app.schemas.goal import GoalProgressUpdate as _GPU
    await goal_service.update_goal_progress(db, goal_id, _GPU(progress=new_progress), organization_id=actor["org_id"])


@router.get("/{goal_id}/projects", response_model=list[ProjectRead])
async def goal_projects(
    goal_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> list[ProjectRead]:
    """List projects linked to a goal."""
    goal = await goal_service.get_goal(db, goal_id, organization_id=actor["org_id"])
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return await project_service.list_projects(
        db, organization_id=actor["org_id"], goal_id=goal_id, limit=limit, offset=offset,
    )


@router.get("/{goal_id}", response_model=GoalRead)
async def get_goal(
    goal_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> GoalRead:
    goal = await goal_service.get_goal(db, goal_id, organization_id=actor["org_id"])
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(
    goal_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> None:
    deleted = await goal_service.delete_goal(db, goal_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Goal not found")
    await record_action(
        db, event_type="goal_deleted", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="goal", entity_id=goal_id,
    )
