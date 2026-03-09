import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectStatusUpdate, ProjectUpdate

logger = logging.getLogger(__name__)


_UPDATE_FIELDS = {"title", "description", "category", "due_date", "goal_id"}


async def create_project(
    db: AsyncSession, data: ProjectCreate, organization_id: int
) -> Project:
    project = Project(**data.model_dump(), organization_id=organization_id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    logger.info("project created id=%d org=%d", project.id, organization_id)
    # Cascade to goal if linked
    if project.goal_id:
        from app.services.goal import recalculate_goal_progress
        await recalculate_goal_progress(db, project.goal_id, organization_id)
    return project


async def list_projects(
    db: AsyncSession, organization_id: int, limit: int = 50, offset: int = 0,
    goal_id: int | None = None,
) -> list[Project]:
    query = (
        select(Project)
        .where(Project.organization_id == organization_id)
        .order_by(Project.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if goal_id is not None:
        query = query.where(Project.goal_id == goal_id)
    result = await db.execute(query)
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
    # Cascade to goal
    if project.goal_id:
        from app.services.goal import recalculate_goal_progress
        await recalculate_goal_progress(db, project.goal_id, organization_id)
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
    old_goal_id = project.goal_id
    for field, value in data.model_dump(exclude_unset=True).items():
        if field in _UPDATE_FIELDS:
            setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    # Cascade goal recalculation if goal link changed
    if project.goal_id and project.goal_id != old_goal_id:
        from app.services.goal import recalculate_goal_progress
        await recalculate_goal_progress(db, project.goal_id, organization_id)
    if old_goal_id and old_goal_id != project.goal_id:
        from app.services.goal import recalculate_goal_progress
        await recalculate_goal_progress(db, old_goal_id, organization_id)
    logger.info("project updated id=%d org=%d", project_id, organization_id)
    return project


async def delete_project(
    db: AsyncSession, project_id: int, organization_id: int,
) -> bool:
    project = await get_project(db, project_id, organization_id)
    if project is None:
        return False
    goal_id = project.goal_id
    await db.delete(project)
    await db.commit()
    # Cascade to goal after project removal
    if goal_id:
        from app.services.goal import recalculate_goal_progress
        await recalculate_goal_progress(db, goal_id, organization_id)
    logger.info("project deleted id=%d org=%d", project_id, organization_id)
    return True
