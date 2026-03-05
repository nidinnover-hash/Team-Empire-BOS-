from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_workspace_id, get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.project import ProjectCreate, ProjectRead, ProjectStatusUpdate, ProjectUpdate
from app.services import project as project_service

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> ProjectRead:
    """Create a project — business or personal."""
    project = await project_service.create_project(db, data, organization_id=actor["org_id"])
    await record_action(
        db,
        event_type="project_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="project",
        entity_id=project.id,
        payload_json={"title": data.title},
    )
    return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> list[ProjectRead]:
    """List all projects, newest first. Use limit/offset for pagination."""
    return await project_service.list_projects(db, limit=limit, offset=offset, organization_id=actor["org_id"])


@router.patch("/{project_id}/status", response_model=ProjectRead)
async def update_status(
    project_id: int,
    data: ProjectStatusUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> ProjectRead:
    """Update a project's status (active|completed|paused|archived)."""
    project = await project_service.update_project_status(db, project_id, data, organization_id=actor["org_id"])
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> ProjectRead:
    project = await project_service.get_project(db, project_id, organization_id=actor["org_id"])
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> ProjectRead:
    project = await project_service.update_project(db, project_id, data, organization_id=actor["org_id"])
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await record_action(
        db, event_type="project_updated", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="project", entity_id=project_id,
    )
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> None:
    deleted = await project_service.delete_project(db, project_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    await record_action(
        db, event_type="project_deleted", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="project", entity_id=project_id,
    )
