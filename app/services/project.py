from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectStatusUpdate


async def create_project(
    db: AsyncSession, data: ProjectCreate, organization_id: int = 1
) -> Project:
    project = Project(**data.model_dump(), organization_id=organization_id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def list_projects(
    db: AsyncSession, limit: int = 50, organization_id: int | None = None
) -> list[Project]:
    query = select(Project)
    if organization_id is not None:
        query = query.where(Project.organization_id == organization_id)
    result = await db.execute(query.order_by(Project.created_at.desc()).limit(limit))
    return list(result.scalars().all())


async def update_project_status(
    db: AsyncSession,
    project_id: int,
    data: ProjectStatusUpdate,
    organization_id: int | None = None,
) -> Project | None:
    query = select(Project).where(Project.id == project_id)
    if organization_id is not None:
        query = query.where(Project.organization_id == organization_id)
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if project is None:
        return None
    project.status = data.status
    await db.commit()
    await db.refresh(project)
    return project
