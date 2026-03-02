import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectStatusUpdate, ProjectUpdate

logger = logging.getLogger(__name__)


_UPDATE_FIELDS = {"title", "description", "category", "due_date"}


async def create_project(
    db: AsyncSession, data: ProjectCreate, organization_id: int
) -> Project:
    project = Project(**data.model_dump(), organization_id=organization_id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    logger.info("project created id=%d org=%d", project.id, organization_id)
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
    project = result.scalar_one_or_none()
    if project is None:
        return None
    project.status = data.status
    await db.commit()
    await db.refresh(project)
    return project


async def get_project(
    db: AsyncSession, project_id: int, organization_id: int,
) -> Project | None:
    result = await db.execute(
        select(Project).where(
            Project.id == project_id, Project.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def update_project(
    db: AsyncSession, project_id: int, data: ProjectUpdate, organization_id: int,
) -> Project | None:
    project = await get_project(db, project_id, organization_id)
    if project is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        if field in _UPDATE_FIELDS:
            setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    logger.info("project updated id=%d org=%d", project_id, organization_id)
    return project


async def delete_project(
    db: AsyncSession, project_id: int, organization_id: int,
) -> bool:
    project = await get_project(db, project_id, organization_id)
    if project is None:
        return False
    await db.delete(project)
    await db.commit()
    logger.info("project deleted id=%d org=%d", project_id, organization_id)
    return True
