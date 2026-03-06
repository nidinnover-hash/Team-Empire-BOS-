from __future__ import annotations

from app.core.config import settings


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
