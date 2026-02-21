from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectStatusUpdate


async def create_project(db: AsyncSession, data: ProjectCreate) -> Project:
    project = Project(**data.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def list_projects(db: AsyncSession, limit: int = 50) -> list[Project]:
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def update_project_status(
    db: AsyncSession, project_id: int, data: ProjectStatusUpdate
) -> Project | None:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return None
    project.status = data.status
    await db.commit()
    await db.refresh(project)
    return project
