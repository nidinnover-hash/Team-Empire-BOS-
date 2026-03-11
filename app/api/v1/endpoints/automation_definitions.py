"""Workflow definition v2 + copilot + templates + runs + insights (extracted from automation.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.automation.bootstrap import (
    workflow_approval_pipeline_enabled_for_org,
    workflow_copilot_enabled_for_org,
    workflow_exec_insights_enabled_for_org,
    workflow_runs_enabled_for_org,
    workflow_v2_enabled_for_org,
)
from app.application.automation.copilot import build_workflow_copilot_plan
from app.core.config import settings
from app.core.deps import get_current_workspace_id, get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.automation import (
    WorkflowApprovalPreviewRead,
    WorkflowDefinitionCreate,
    WorkflowDefinitionRead,
    WorkflowDefinitionUpdate,
    WorkflowRunListItem,
    WorkflowRunRead,
    WorkflowRunRequest,
)
from app.schemas.workflow_plan import WorkflowPlanDraftRead, WorkflowPlanRequest
from app.services import automation as automation_service

router = APIRouter(prefix="/automations", tags=["Automations"])


async def _require_workflow_v2(db: AsyncSession, org_id: int) -> None:
    if not await workflow_v2_enabled_for_org(db, org_id):
        raise HTTPException(status_code=404, detail="Not found")


async def _require_workflow_runs(db: AsyncSession, org_id: int) -> None:
    if not await workflow_runs_enabled_for_org(db, org_id):
        raise HTTPException(status_code=404, detail="Not found")


async def _require_workflow_approval_pipeline(db: AsyncSession, org_id: int) -> None:
    if not await workflow_approval_pipeline_enabled_for_org(db, org_id):
        raise HTTPException(status_code=404, detail="Not found")


async def _require_workflow_copilot(db: AsyncSession, org_id: int) -> None:
    if not await workflow_copilot_enabled_for_org(db, org_id):
        raise HTTPException(status_code=404, detail="Not found")


async def _require_workflow_exec_insights(db: AsyncSession, org_id: int) -> None:
    if not await workflow_exec_insights_enabled_for_org(db, org_id):
        raise HTTPException(status_code=404, detail="Not found")


# ── Workflow Definitions ─────────────────────────────────────────────────────


@router.get("/workflow-definitions", response_model=list[WorkflowDefinitionRead])
async def list_workflow_definitions(
    status: str | None = Query(None, max_length=20),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[WorkflowDefinitionRead]:
    await _require_workflow_v2(db, int(actor["org_id"]))
    rows = await automation_service.list_workflow_definitions(
        db, organization_id=int(actor["org_id"]), status=status, limit=limit,
    )
    return [WorkflowDefinitionRead.model_validate(row) for row in rows]


@router.post("/workflow-definitions", response_model=WorkflowDefinitionRead, status_code=201)
async def create_workflow_definition(
    data: WorkflowDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> WorkflowDefinitionRead:
    await _require_workflow_v2(db, int(actor["org_id"]))
    row = await automation_service.create_workflow_definition(
        db, organization_id=int(actor["org_id"]),
        workspace_id=workspace_id, actor_user_id=int(actor["id"]), data=data,
    )
    return WorkflowDefinitionRead.model_validate(row)


@router.get("/workflow-definitions/{workflow_definition_id}", response_model=WorkflowDefinitionRead)
async def get_workflow_definition(
    workflow_definition_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> WorkflowDefinitionRead:
    await _require_workflow_v2(db, int(actor["org_id"]))
    row = await automation_service.get_workflow_definition(
        db, organization_id=int(actor["org_id"]),
        workflow_definition_id=workflow_definition_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    return WorkflowDefinitionRead.model_validate(row)


@router.patch("/workflow-definitions/{workflow_definition_id}", response_model=WorkflowDefinitionRead)
async def update_workflow_definition(
    workflow_definition_id: int,
    data: WorkflowDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WorkflowDefinitionRead:
    await _require_workflow_v2(db, int(actor["org_id"]))
    row = await automation_service.update_workflow_definition(
        db, organization_id=int(actor["org_id"]),
        workflow_definition_id=workflow_definition_id,
        actor_user_id=int(actor["id"]), data=data,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    return WorkflowDefinitionRead.model_validate(row)


@router.post("/workflow-definitions/{workflow_definition_id}/publish", response_model=WorkflowDefinitionRead)
async def publish_workflow_definition(
    workflow_definition_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WorkflowDefinitionRead:
    await _require_workflow_v2(db, int(actor["org_id"]))
    row = await automation_service.publish_workflow_definition(
        db, organization_id=int(actor["org_id"]),
        workflow_definition_id=workflow_definition_id,
        actor_user_id=int(actor["id"]),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    return WorkflowDefinitionRead.model_validate(row)


@router.post("/workflow-definitions/{workflow_definition_id}/run-preview", response_model=WorkflowApprovalPreviewRead)
async def preview_workflow_definition_run(
    workflow_definition_id: int,
    payload: WorkflowRunRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> WorkflowApprovalPreviewRead:
    await _require_workflow_v2(db, int(actor["org_id"]))
    preview = await automation_service.preview_workflow_run(
        db, organization_id=int(actor["org_id"]),
        workspace_id=workspace_id, actor_user_id=int(actor["id"]),
        workflow_definition_id=workflow_definition_id,
        input_json=payload.input_json,
    )
    if preview is None:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    return WorkflowApprovalPreviewRead.model_validate(preview)


@router.post("/workflow-definitions/{workflow_definition_id}/run", response_model=WorkflowRunRead)
async def run_workflow_definition(
    workflow_definition_id: int,
    payload: WorkflowRunRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> WorkflowRunRead:
    await _require_workflow_approval_pipeline(db, int(actor["org_id"]))
    run = await automation_service.run_workflow_definition(
        db, organization_id=int(actor["org_id"]),
        workspace_id=workspace_id, actor_user_id=int(actor["id"]),
        workflow_definition_id=workflow_definition_id,
        trigger_source=payload.trigger_source,
        input_json=payload.input_json,
        trigger_signal_id=payload.trigger_signal_id,
        idempotency_key=payload.idempotency_key,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Published workflow definition not found")
    detail = await automation_service.get_workflow_run_detail(
        db, organization_id=int(actor["org_id"]),
        workflow_run_id=int(run.id),
    )
    assert detail is not None
    return WorkflowRunRead.model_validate({**detail["run"].__dict__, "step_runs": detail["step_runs"]})


# ── Workflow Runs ────────────────────────────────────────────────────────────


@router.get("/workflow-runs", response_model=list[WorkflowRunListItem])
async def list_workflow_runs(
    status: str | None = Query(None, max_length=30),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[WorkflowRunListItem]:
    await _require_workflow_runs(db, int(actor["org_id"]))
    rows = await automation_service.list_workflow_runs_v2(
        db, organization_id=int(actor["org_id"]), status=status, limit=limit,
    )
    return [WorkflowRunListItem.model_validate(row) for row in rows]


@router.get("/workflow-runs/{workflow_run_id}", response_model=WorkflowRunRead)
async def get_workflow_run(
    workflow_run_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> WorkflowRunRead:
    await _require_workflow_runs(db, int(actor["org_id"]))
    detail = await automation_service.get_workflow_run_detail(
        db, organization_id=int(actor["org_id"]),
        workflow_run_id=workflow_run_id,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return WorkflowRunRead.model_validate({**detail["run"].__dict__, "step_runs": detail["step_runs"]})


@router.post("/workflow-runs/{workflow_run_id}/retry", response_model=WorkflowRunListItem)
async def retry_workflow_run(
    workflow_run_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WorkflowRunListItem:
    await _require_workflow_runs(db, int(actor["org_id"]))
    run = await automation_service.retry_workflow_run_v2(
        db, organization_id=int(actor["org_id"]),
        actor_user_id=int(actor["id"]), workflow_run_id=workflow_run_id,
    )
    if run is None:
        raise HTTPException(status_code=409, detail="Workflow run cannot be retried")
    return WorkflowRunListItem.model_validate(run)


@router.post("/workflow-runs/{workflow_run_id}/pause", response_model=WorkflowRunListItem)
async def pause_workflow_run(
    workflow_run_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WorkflowRunListItem:
    await _require_workflow_runs(db, int(actor["org_id"]))
    run = await automation_service.pause_workflow_run_v2(
        db, organization_id=int(actor["org_id"]),
        actor_user_id=int(actor["id"]), workflow_run_id=workflow_run_id,
    )
    if run is None:
        raise HTTPException(status_code=409, detail="Workflow run cannot be paused")
    return WorkflowRunListItem.model_validate(run)


@router.post("/workflow-runs/{workflow_run_id}/resume", response_model=WorkflowRunListItem)
async def resume_workflow_run(
    workflow_run_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WorkflowRunListItem:
    await _require_workflow_runs(db, int(actor["org_id"]))
    run = await automation_service.resume_workflow_run_v2(
        db, organization_id=int(actor["org_id"]),
        actor_user_id=int(actor["id"]), workflow_run_id=workflow_run_id,
    )
    if run is None:
        raise HTTPException(status_code=409, detail="Workflow run cannot be resumed")
    return WorkflowRunListItem.model_validate(run)


# ── Copilot ──────────────────────────────────────────────────────────────────


@router.post("/copilot/plan", response_model=WorkflowPlanDraftRead)
async def workflow_copilot_plan(
    data: WorkflowPlanRequest,
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> WorkflowPlanDraftRead:
    await _require_workflow_copilot(db, int(actor["org_id"]))
    payload = await build_workflow_copilot_plan(
        actor=actor, organization_id=int(actor["org_id"]),
        workspace_id=data.workspace_id if data.workspace_id is not None else workspace_id,
        intent=data.intent, constraints=data.constraints,
        available_integrations=data.available_integrations,
    )
    return WorkflowPlanDraftRead.model_validate(payload)


@router.post("/copilot/plan-and-save", response_model=WorkflowDefinitionRead)
async def workflow_copilot_plan_and_save(
    data: WorkflowPlanRequest,
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
    workspace_id: int = Depends(get_current_workspace_id),
) -> WorkflowDefinitionRead:
    """Generate a workflow plan from natural language AND save it as a draft definition."""
    await _require_workflow_copilot(db, int(actor["org_id"]))
    org_id = int(actor["org_id"])
    effective_ws = data.workspace_id if data.workspace_id is not None else workspace_id
    payload = await build_workflow_copilot_plan(
        actor=actor, organization_id=org_id, workspace_id=effective_ws,
        intent=data.intent, constraints=data.constraints,
        available_integrations=data.available_integrations,
    )
    from app.schemas.workflow_definition import WorkflowDefinitionStep

    create_data = WorkflowDefinitionCreate(
        name=str(payload.get("name") or f"Copilot: {data.intent[:60]}"),
        description=str(payload.get("summary") or data.intent[:200]),
        trigger_mode=str(payload.get("trigger_mode") or "manual"),
        steps=[
            WorkflowDefinitionStep(
                key=str(s.get("key") or f"step-{i}"),
                name=str(s.get("name") or f"Step {i + 1}"),
                action_type=str(s.get("action_type") or "noop"),
                params=dict(s.get("params") or {}),
                requires_approval=bool(s.get("requires_approval")),
            )
            for i, s in enumerate(payload.get("steps") or [])
        ],
        risk_level=str(payload.get("risk_level") or "medium"),
    )
    row = await automation_service.create_workflow_definition(
        db, organization_id=org_id, workspace_id=effective_ws,
        actor_user_id=int(actor["id"]), data=create_data,
    )
    await record_action(
        db, event_type="workflow_copilot_generated", actor_user_id=int(actor["id"]),
        organization_id=org_id, entity_type="workflow_definition",
        entity_id=row.id, payload_json={"intent": data.intent[:500], "confidence": payload.get("confidence")},
    )
    return WorkflowDefinitionRead.model_validate(row)


# ── Insights ─────────────────────────────────────────────────────────────────


@router.get("/insights")
async def get_workflow_insights(
    days: int = Query(30, ge=1, le=365),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Workflow execution analytics: success rates, step timings, failure patterns."""
    await _require_workflow_exec_insights(db, int(actor["org_id"]))
    from app.services.workflow_insights import get_full_insights
    return await get_full_insights(db, organization_id=int(actor["org_id"]), days=days)


# ── Templates ────────────────────────────────────────────────────────────────


@router.get("/templates")
async def list_workflow_templates(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[dict]:
    """Return built-in workflow template presets."""
    await _require_workflow_v2(db, int(actor["org_id"]))
    from app.services.workflow_templates import get_templates
    return get_templates()


@router.post("/templates/{template_id}/create", response_model=WorkflowDefinitionRead, status_code=201)
async def create_from_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> WorkflowDefinitionRead:
    """Create a draft workflow definition from a built-in template."""
    await _require_workflow_v2(db, int(actor["org_id"]))
    from app.services.workflow_templates import get_template_by_id
    tpl = get_template_by_id(template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    create_data = WorkflowDefinitionCreate(
        name=tpl["name"], description=tpl["description"],
        trigger_mode=tpl.get("trigger_mode", "manual"),
        steps=tpl["steps"], risk_level=tpl.get("risk_level", "medium"),
    )
    row = await automation_service.create_workflow_definition(
        db, organization_id=int(actor["org_id"]),
        workspace_id=workspace_id, actor_user_id=int(actor["id"]),
        data=create_data,
    )
    await record_action(
        db, event_type="workflow_template_used", actor_user_id=int(actor["id"]),
        organization_id=int(actor["org_id"]), entity_type="workflow_definition",
        entity_id=row.id, payload_json={"template_id": template_id, "template_name": tpl["name"]},
    )
    return WorkflowDefinitionRead.model_validate(row)


# ── Job Queue Status ─────────────────────────────────────────────────────────


@router.get("/job-queue-stats")
async def get_job_queue_stats(
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return job queue health metrics."""
    from app.services.job_queue import get_queue_stats
    return await get_queue_stats(db, organization_id=int(actor["org_id"]))
