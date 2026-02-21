from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.project import ProjectCreate, ProjectRead, ProjectStatusUpdate
from app.services import project as project_service

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    """Create a project — business or personal."""
    return await project_service.create_project(db, data)


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    db: AsyncSession = Depends(get_db),
) -> list[ProjectRead]:
    """List all projects, newest first."""
    return await project_service.list_projects(db)


@router.patch("/{project_id}/status", response_model=ProjectRead)
async def update_status(
    project_id: int,
    data: ProjectStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProjectRead:
    """Update a project's status (active|completed|paused|archived)."""
    project = await project_service.update_project_status(db, project_id, data)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project
