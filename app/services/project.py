from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectStatusUpdate


async def create_project(
    db: AsyncSession, data: ProjectCreate, organization_id: int
) -> Project:
    project = Project(**data.model_dump(), organization_id=organization_id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def list_projects(
    db: AsyncSession, organization_id: int, limit: int = 50, offset: int = 0
) -> list[Project]:
    result = await db.execute(
        select(Project)
        .where(Project.organization_id == organization_id)
        .order_by(Project.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_project_status(
    db: AsyncSession,
    project_id: int,
    data: ProjectStatusUpdate,
    organization_id: int,
) -> Project | None:
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == organization_id,
        )
    )
    project = cast(Project | None, result.scalar_one_or_none())
    if project is None:
        return None
    project.status = data.status
    await db.commit()
    await db.refresh(project)
    return project
