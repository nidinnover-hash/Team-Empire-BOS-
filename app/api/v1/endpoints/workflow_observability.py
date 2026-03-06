from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.automation import observability as workflow_obs
from app.core.config import settings
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.approval import ApprovalRead
from app.schemas.observability import SignalRead
from app.schemas.workflow_run import WorkflowRunListItem, WorkflowRunRead, WorkflowStepRunRead

router = APIRouter(prefix="/workflow-observability", tags=["Workflow Observability"])


def _require_workflow_observability() -> None:
    if not settings.FEATURE_WORKFLOW_OBSERVABILITY:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/summary")
async def workflow_summary(
    days: int = Query(default=7, ge=1, le=90),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    _require_workflow_observability()
    return await workflow_obs.get_workflow_observability_summary(
        db,
        organization_id=int(actor["org_id"]),
        days=days,
    )


@router.get("/runs", response_model=list[WorkflowRunListItem])
async def workflow_runs(
    status: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=100, ge=1, le=200),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowRunListItem]:
    _require_workflow_observability()
    rows = await workflow_obs.list_workflow_observability_runs(
        db,
        organization_id=int(actor["org_id"]),
        status=status,
        limit=limit,
    )
    return [WorkflowRunListItem.model_validate(row) for row in rows]


@router.get("/runs/{workflow_run_id}", response_model=WorkflowRunRead)
async def workflow_run_detail(
    workflow_run_id: int,
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunRead:
    _require_workflow_observability()
    detail = await workflow_obs.get_workflow_observability_run_detail(
        db,
        organization_id=int(actor["org_id"]),
        workflow_run_id=workflow_run_id,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return WorkflowRunRead.model_validate({**detail["run"].__dict__, "step_runs": [WorkflowStepRunRead.model_validate(item) for item in detail["step_runs"]]})


@router.get("/failures", response_model=list[WorkflowRunListItem])
async def workflow_failures(
    limit: int = Query(default=50, ge=1, le=200),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowRunListItem]:
    _require_workflow_observability()
    rows = await workflow_obs.list_workflow_failures(db, organization_id=int(actor["org_id"]), limit=limit)
    return [WorkflowRunListItem.model_validate(row) for row in rows]


@router.get("/approvals", response_model=list[ApprovalRead])
async def workflow_approvals(
    limit: int = Query(default=50, ge=1, le=200),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalRead]:
    _require_workflow_observability()
    rows = await workflow_obs.list_workflow_approval_backlog(db, organization_id=int(actor["org_id"]), limit=limit)
    return [ApprovalRead.model_validate(row, from_attributes=True) for row in rows]


@router.get("/ai-plans", response_model=list[SignalRead])
async def workflow_ai_plans(
    limit: int = Query(default=50, ge=1, le=200),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[SignalRead]:
    _require_workflow_observability()
    rows = await workflow_obs.list_ai_workflow_plans(db, organization_id=int(actor["org_id"]), limit=limit)
    return [
        SignalRead(
            id=row.id,
            signal_id=row.signal_id,
            organization_id=row.organization_id,
            workspace_id=row.workspace_id,
            actor_user_id=row.actor_user_id,
            topic=row.topic,
            category=row.category,
            source=row.source,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            correlation_id=row.correlation_id,
            causation_id=row.causation_id,
            request_id=row.request_id,
            summary_text=row.summary_text,
            payload=row.payload_json or {},
            metadata=row.metadata_json or {},
            occurred_at=row.occurred_at,
            created_at=row.created_at,
        )
        for row in rows
    ]
