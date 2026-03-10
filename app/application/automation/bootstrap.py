from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import feature_flags


def workflow_v2_enabled() -> bool:
    return bool(settings.FEATURE_WORKFLOW_V2)


def workflow_runs_enabled() -> bool:
    return bool(settings.FEATURE_WORKFLOW_V2 and settings.FEATURE_WORKFLOW_RUNS)


def workflow_approval_pipeline_enabled() -> bool:
    return bool(
        settings.FEATURE_WORKFLOW_V2
        and settings.FEATURE_WORKFLOW_RUNS
        and settings.FEATURE_WORKFLOW_APPROVAL_PIPELINE
    )


def workflow_exec_insights_enabled() -> bool:
    return bool(
        settings.FEATURE_WORKFLOW_V2
        and settings.FEATURE_WORKFLOW_RUNS
        and settings.FEATURE_WORKFLOW_EXEC_INSIGHTS
    )


async def workflow_v2_enabled_for_org(db: AsyncSession, organization_id: int) -> bool:
    return await feature_flags.is_effective_feature_enabled(
        db,
        organization_id=organization_id,
        flag_name="workflow_v2",
        default=bool(settings.FEATURE_WORKFLOW_V2),
    )


async def workflow_runs_enabled_for_org(db: AsyncSession, organization_id: int) -> bool:
    v2 = await workflow_v2_enabled_for_org(db, organization_id)
    if not v2:
        return False
    return await feature_flags.is_effective_feature_enabled(
        db,
        organization_id=organization_id,
        flag_name="workflow_runs",
        default=bool(settings.FEATURE_WORKFLOW_RUNS),
    )


async def workflow_approval_pipeline_enabled_for_org(db: AsyncSession, organization_id: int) -> bool:
    runs_enabled = await workflow_runs_enabled_for_org(db, organization_id)
    if not runs_enabled:
        return False
    return await feature_flags.is_effective_feature_enabled(
        db,
        organization_id=organization_id,
        flag_name="workflow_approval_pipeline",
        default=bool(settings.FEATURE_WORKFLOW_APPROVAL_PIPELINE),
    )


async def workflow_exec_insights_enabled_for_org(db: AsyncSession, organization_id: int) -> bool:
    runs_enabled = await workflow_runs_enabled_for_org(db, organization_id)
    if not runs_enabled:
        return False
    return await feature_flags.is_effective_feature_enabled(
        db,
        organization_id=organization_id,
        flag_name="workflow_exec_insights",
        default=bool(settings.FEATURE_WORKFLOW_EXEC_INSIGHTS),
    )


async def workflow_observability_enabled_for_org(db: AsyncSession, organization_id: int) -> bool:
    runs_enabled = await workflow_runs_enabled_for_org(db, organization_id)
    if not runs_enabled:
        return False
    return await feature_flags.is_effective_feature_enabled(
        db,
        organization_id=organization_id,
        flag_name="workflow_observability",
        default=bool(settings.FEATURE_WORKFLOW_OBSERVABILITY),
    )


async def workflow_copilot_enabled_for_org(db: AsyncSession, organization_id: int) -> bool:
    v2 = await workflow_v2_enabled_for_org(db, organization_id)
    if not v2:
        return False
    return await feature_flags.is_effective_feature_enabled(
        db,
        organization_id=organization_id,
        flag_name="workflow_copilot",
        default=bool(settings.FEATURE_WORKFLOW_COPILOT),
    )
