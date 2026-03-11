import logging
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.idempotency import (
    IdempotencyConflictError,
    build_fingerprint,
    get_cached_response,
    store_response,
)
from app.core.privacy import sanitize_response_payload
from app.core.rbac import require_roles
from app.core.request_context import get_current_request_id
from app.logs.audit import record_action
from app.models.approval import Approval
from app.schemas.daily_run import DailyRunRead
from app.schemas.event import EventRead
from app.schemas.intelligence import DecisionTraceCreate
from app.schemas.ops import (
    CicdSyncResultRead,
    CloneDispatchItemRead,
    CloneDispatchRequest,
    CloneFeedbackCreate,
    CloneProfileRead,
    CloneProfileUpsert,
    CloneScoreRead,
    CloneSummaryRead,
    CloneTrainingRunRead,
    DailyRunResponse,
    DecisionLogCreate,
    DecisionLogRead,
    EmployeeCreate,
    EmployeeIdentityMapRead,
    EmployeeIdentityMapUpsert,
    EmployeeRead,
    EmployeeUpdate,
    PolicyRuleRead,
    RoleTrainingPlanRead,
    RoleTrainingPlanStatusUpdate,
    SyncResultRead,
    WeeklyMetricsResponse,
    WeeklyReportRead,
)
from app.schemas.project import ProjectCreate, ProjectRead, ProjectStatusUpdate
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services import briefing as briefing_service
from app.services import (
    clone_brain,
    clone_control,
    email_service,
    metrics_service,
    policy_service,
    report_service,
    signal_ingestion,
    task_engine,
)
from app.services import daily_run as daily_run_service
from app.services import employee as employee_service
from app.services import event as event_service
from app.services import intelligence as intelligence_service
from app.services import project as project_service
from app.services import task as task_service

router = APIRouter(prefix="/ops", tags=["Ops"])
logger = logging.getLogger(__name__)


async def run_daily_run_workflow(
    db: AsyncSession,
    org_id: int,
    actor_user_id: int,
    actor_role: str | None = None,
    draft_email_limit: int = 5,
    team: str | None = None,
) -> dict:
    run_date = date.today()
    team_filter = team or "*"

    existing_run = await daily_run_service.get_daily_run_by_scope(
        db=db,
        organization_id=org_id,
        run_date=run_date,
        team_filter=team_filter,
    )
    if existing_run:
        payload = existing_run.result_json or {}
        return {
            "status": "already_completed",
            "message": "Daily run already executed for this date/scope. Returning existing result.",
            "daily_run_id": existing_run.id,
            "run_date": str(existing_run.run_date),
            "team_filter": existing_run.team_filter,
            "idempotent_reuse": True,
            "requires_approval": True,
            **payload,
        }

    run = await daily_run_service.create_daily_run(
        db=db,
        organization_id=org_id,
        run_date=run_date,
        team_filter=team_filter,
        requested_by=actor_user_id,
        status="running",
    )

    try:
        executive = await briefing_service.get_executive_briefing(db=db, org_id=org_id)

        plans = await task_engine.draft_team_plans(
            db=db,
            org_id=org_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            team=team,
        )

        unread_emails = await email_service.list_emails(
            db=db,
            org_id=org_id,
            limit=max(draft_email_limit * 3, draft_email_limit),
            unread_only=True,
        )
        drafted_email_ids: list[int] = []
        for email in unread_emails:
            if len(drafted_email_ids) >= draft_email_limit:
                break
            if not email.body_text or email.reply_sent or email.draft_reply:
                continue
            drafted = await email_service.draft_reply(
                db=db,
                email_id=email.id,
                org_id=org_id,
                actor_user_id=actor_user_id,
                instruction="Daily run draft: concise, actionable, professional.",
            )
            if drafted:
                drafted_email_ids.append(email.id)

        pending_result = await db.execute(
            select(func.count(Approval.id)).where(
                Approval.organization_id == org_id,
                Approval.status == "pending",
            )
        )
        pending_approvals = int(pending_result.scalar() or 0)

        result_payload = {
            "executive_summary": executive["team_summary"],
            "drafted_plan_count": len(plans),
            "drafted_plan_ids": [p.id for p in plans],
            "drafted_email_count": len(drafted_email_ids),
            "drafted_email_ids": drafted_email_ids,
            "pending_approvals": pending_approvals,
        }

        run_event = await record_action(
            db=db,
            organization_id=org_id,
            event_type="daily_run_drafted",
            actor_user_id=actor_user_id,
            entity_type="ops_daily_run",
            entity_id=run.id,
            payload_json={
                "drafted_plan_count": len(plans),
                "drafted_email_count": len(drafted_email_ids),
                "pending_approvals": pending_approvals,
                "team_filter": team_filter,
                "run_date": str(run_date),
            },
        )

        confidence_score = min(
            1.0,
            0.2
            + (0.25 if len(plans) > 0 else 0.0)
            + (0.25 if len(drafted_email_ids) > 0 else 0.0)
            + (0.15 if pending_approvals == 0 else 0.0)
            + (0.15 if pending_approvals <= 3 else 0.0),
        )
        risk_tier = "low" if confidence_score >= 0.8 else ("medium" if confidence_score >= 0.55 else "high")
        confidence_reasoning = [
            "Team plan drafts were generated." if len(plans) > 0 else "No team plan drafts were generated.",
            "Email draft generation succeeded." if len(drafted_email_ids) > 0 else "No email drafts were generated.",
            (
                "Pending approvals are low."
                if pending_approvals <= 3
                else "Pending approvals are elevated and may slow execution."
            ),
        ]
        trace = await intelligence_service.create_decision_trace(
            db=db,
            data=DecisionTraceCreate(
                organization_id=org_id,
                trace_type="daily_run",
                title=f"Daily Run {run_date.isoformat()} ({team_filter})",
                summary=(
                    f"Drafted {len(plans)} plans and {len(drafted_email_ids)} email replies; "
                    f"{pending_approvals} approvals pending."
                ),
                confidence_score=confidence_score,
                signals_json={
                    "team_filter": team_filter,
                    "drafted_plan_count": len(plans),
                    "drafted_email_count": len(drafted_email_ids),
                    "pending_approvals": pending_approvals,
                    "risk_tier": risk_tier,
                    "reasoning": confidence_reasoning,
                },
                actor_user_id=actor_user_id,
                request_id=get_current_request_id(),
                daily_run_id=run.id,
                source_event_id=run_event.id,
            ),
        )
        result_payload["decision_trace_id"] = trace.id
        result_payload["confidence_score"] = confidence_score
        result_payload["risk_tier"] = risk_tier
        result_payload["confidence_reasoning"] = confidence_reasoning

        await daily_run_service.complete_daily_run(
            db=db,
            run_id=run.id,
            organization_id=org_id,
            status="completed",
            drafted_plan_count=len(plans),
            drafted_email_count=len(drafted_email_ids),
            pending_approvals=pending_approvals,
            result_json=result_payload,
        )

        return {
            "status": "draft_only_completed",
            "message": "Daily run created drafts only. Nothing was sent or executed.",
            "daily_run_id": run.id,
            "run_date": str(run_date),
            "team_filter": team_filter,
            "idempotent_reuse": False,
            "requires_approval": True,
            **result_payload,
        }
    except (SQLAlchemyError, RuntimeError, ValueError, TypeError):
        try:
            await daily_run_service.complete_daily_run(
                db=db,
                run_id=run.id,
                organization_id=org_id,
                status="failed",
                drafted_plan_count=0,
                drafted_email_count=0,
                pending_approvals=0,
                result_json={},
            )
        except (SQLAlchemyError, RuntimeError, ValueError, TypeError) as exc:
            logger.warning(
                "Failed to mark daily run as failed (run_id=%s org_id=%s): %s",
                run.id,
                org_id,
                type(exc).__name__,
            )
        raise


@router.post("/projects", response_model=ProjectRead, status_code=201)
async def create_project_ops(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ProjectRead:
    project = await project_service.create_project(
        db, data, organization_id=user["org_id"]
    )
    await record_action(
        db,
        event_type="project_created",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="project",
        entity_id=project.id,
        payload_json={"title": project.title, "category": project.category},
    )
    return project


@router.patch("/projects/{project_id}/status", response_model=ProjectRead)
async def update_project_status_ops(
    project_id: int,
    data: ProjectStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ProjectRead:
    project = await project_service.update_project_status(
        db, project_id, data, organization_id=user["org_id"]
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await record_action(
        db,
        event_type="project_status_updated",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="project",
        entity_id=project.id,
        payload_json={"status": project.status},
    )
    return project


@router.post("/tasks", response_model=TaskRead, status_code=201)
async def create_task_ops(
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> TaskRead:
    task = await task_service.create_task(db, data, organization_id=user["org_id"])
    await record_action(
        db,
        event_type="task_created",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="task",
        entity_id=task.id,
        payload_json={"title": task.title, "priority": task.priority},
    )
    return task


@router.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task_ops(
    task_id: int,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> TaskRead:
    task = await task_service.update_task(
        db, task_id, data, organization_id=user["org_id"]
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await record_action(
        db,
        event_type="task_updated",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="task",
        entity_id=task.id,
        payload_json={"is_done": task.is_done},
    )
    return task


@router.get("/events", response_model=list[EventRead])
async def list_events_ops(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    actor_user_id: int | None = Query(None),
    event_date: date | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[EventRead]:
    events = await event_service.list_events(
        db,
        organization_id=user["org_id"],
        actor_user_id=actor_user_id,
        event_date=event_date,
        limit=limit,
    )
    safe_events: list[EventRead] = []
    for event in events:
        data = EventRead.model_validate(event).model_dump()
        data["payload_json"] = sanitize_response_payload(data.get("payload_json", {}))
        safe_events.append(EventRead(**data))
    return safe_events


@router.post("/daily-run", response_model=DailyRunResponse)
async def daily_run_ops(
    draft_email_limit: int = Query(5, ge=0, le=20),
    team: str | None = Query(None, max_length=100),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """
    Daily run orchestrator (draft-only).
    - Pulls executive snapshot
    - Drafts team plans
    - Drafts top email replies
    - Creates approvals only
    Never auto-sends or auto-executes anything.
    """
    org_id = int(user["org_id"])
    scope = f"ops_daily_run:{org_id}:{team or '*'}:{draft_email_limit}"
    fingerprint = build_fingerprint(
        {"org_id": org_id, "draft_email_limit": draft_email_limit, "team": team or "*"}
    )
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return cached
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict: this key was already used with a different request body") from exc

    result = await run_daily_run_workflow(
        db=db,
        org_id=org_id,
        actor_user_id=int(user["id"]),
        actor_role=str(user["role"]),
        draft_email_limit=draft_email_limit,
        team=team,
    )
    if idempotency_key:
        store_response(scope, idempotency_key, result, fingerprint=fingerprint)
    return result


@router.get("/daily-runs", response_model=list[DailyRunRead])
async def list_daily_runs_ops(
    run_date: date | None = Query(None),
    limit: int = Query(30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[DailyRunRead]:
    return await daily_run_service.list_daily_runs(
        db=db,
        organization_id=int(user["org_id"]),
        run_date=run_date,
        limit=limit,
    )
@router.post("/employees", response_model=EmployeeRead, status_code=201)
async def create_employee(
    data: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> EmployeeRead:
    emp = await employee_service.create_or_update_employee(
        db=db, org_id=int(user["org_id"]), data=data,
    )
    await record_action(
        db,
        event_type="employee_created",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="employee",
        entity_id=emp.id,
        payload_json={"name": emp.name, "email": emp.email},
    )
    return emp


@router.get("/employees", response_model=list[EmployeeRead])
async def list_employees(
    active_only: bool = Query(True),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[EmployeeRead]:
    return await employee_service.list_employees(
        db=db, org_id=int(user["org_id"]), active_only=active_only, skip=skip, limit=limit,
    )


@router.get("/employees/{employee_id}", response_model=EmployeeRead)
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> EmployeeRead:
    emp = await employee_service.get_employee(
        db=db, org_id=int(user["org_id"]), employee_id=employee_id,
    )
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@router.patch("/employees/{employee_id}", response_model=EmployeeRead)
async def update_employee(
    employee_id: int,
    data: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> EmployeeRead:
    emp = await employee_service.update_employee(
        db=db, org_id=int(user["org_id"]), employee_id=employee_id, data=data,
    )
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await record_action(
        db,
        event_type="employee_updated",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="employee",
        entity_id=emp.id,
        payload_json={"name": emp.name, "email": emp.email},
    )
    return emp


@router.post("/employees/{employee_id}/offboard", response_model=EmployeeRead)
async def offboard_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> EmployeeRead:
    emp = await employee_service.offboard_employee(
        db=db, org_id=int(user["org_id"]), employee_id=employee_id,
    )
    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await record_action(
        db,
        event_type="employee_offboarded",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="employee",
        entity_id=emp.id,
        payload_json={"name": emp.name, "email": emp.email},
    )
    return emp
@router.post("/sync/clickup", response_model=SyncResultRead)
async def sync_clickup_signals(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Ingest ClickUp tasks as integration signals. Read-only, no external writes."""
    org_id = int(user["org_id"])
    result = await signal_ingestion.ingest_clickup_signals(db, org_id)
    await record_action(
        db,
        event_type="ops_sync_clickup",
        actor_user_id=user["id"],
        organization_id=org_id,
        entity_type="integration_signal",
        entity_id=0,
        payload_json={"synced": result.get("synced", 0)},
    )
    return result


@router.post("/sync/github", response_model=SyncResultRead)
async def sync_github_signals(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Ingest GitHub PRs and issues as integration signals. Read-only, no external writes."""
    org_id = int(user["org_id"])
    result = await signal_ingestion.ingest_github_signals(db, org_id)
    await record_action(
        db,
        event_type="ops_sync_github",
        actor_user_id=user["id"],
        organization_id=org_id,
        entity_type="integration_signal",
        entity_id=0,
        payload_json={"synced": result.get("synced", 0)},
    )
    return result


@router.post("/sync/github-cicd", response_model=CicdSyncResultRead)
async def sync_github_cicd_signals(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Ingest GitHub Actions workflow runs and deployments as integration signals. Read-only."""
    org_id = int(user["org_id"])
    result = await signal_ingestion.ingest_github_cicd_signals(db, org_id)
    await record_action(
        db,
        event_type="ops_sync_github_cicd",
        actor_user_id=user["id"],
        organization_id=org_id,
        entity_type="integration_signal",
        entity_id=0,
        payload_json={
            "workflow_runs": result.get("workflow_runs", 0),
            "deployments": result.get("deployments", 0),
        },
    )
    return result


@router.post("/sync/gmail", response_model=SyncResultRead)
async def sync_gmail_signals(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Ingest Gmail metadata as integration signals. Respects WORK_EMAIL_DOMAINS allowlist. No body storage."""
    org_id = int(user["org_id"])
    result = await signal_ingestion.ingest_gmail_signals(db, org_id)
    await record_action(
        db,
        event_type="ops_sync_gmail",
        actor_user_id=user["id"],
        organization_id=org_id,
        entity_type="integration_signal",
        entity_id=0,
        payload_json={"synced": result.get("synced", 0), "skipped": result.get("skipped_non_work", 0)},
    )
    return result
@router.post("/compute/weekly-metrics", response_model=WeeklyMetricsResponse)
async def compute_weekly_metrics(
    weeks: int = Query(1, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Compute weekly metrics from ingested signals for the last N weeks."""
    org_id = int(user["org_id"])
    result = await metrics_service.compute_weekly_metrics(db, org_id, weeks=weeks)
    await record_action(
        db,
        event_type="ops_compute_metrics",
        actor_user_id=user["id"],
        organization_id=org_id,
        entity_type="metrics",
        entity_id=0,
        payload_json=result,
    )
    return result
@router.get("/reports/weekly", response_model=WeeklyReportRead | None)
async def get_weekly_report(
    week_start: date = Query(...),
    report_type: str = Query(..., pattern="^(team_health|project_risk|founder_review)$"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WeeklyReportRead | None:
    return await report_service.get_report(db, int(user["org_id"]), week_start, report_type)


@router.post("/reports/weekly", response_model=WeeklyReportRead, status_code=201)
async def generate_weekly_report(
    week_start: date = Query(...),
    report_type: str = Query(..., pattern="^(team_health|project_risk|founder_review)$"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WeeklyReportRead:
    """Generate a weekly report from computed metrics."""
    org_id = int(user["org_id"])
    report = await report_service.generate_weekly_report(db, org_id, week_start, report_type)
    await record_action(
        db,
        event_type="ops_report_generated",
        actor_user_id=user["id"],
        organization_id=org_id,
        entity_type="weekly_report",
        entity_id=report.id,
        payload_json={"week_start": str(week_start), "report_type": report_type},
    )
    return report
@router.post("/decision-log", response_model=DecisionLogRead, status_code=201)
async def create_decision(
    data: DecisionLogCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DecisionLogRead:
    org_id = int(user["org_id"])
    entry = await policy_service.create_decision(db, org_id, int(user["id"]), data)
    await record_action(
        db,
        event_type="decision_logged",
        actor_user_id=user["id"],
        organization_id=org_id,
        entity_type="decision_log",
        entity_id=entry.id,
        payload_json={"decision_type": entry.decision_type, "context": entry.context[:100]},
    )
    return entry


@router.get("/decision-log", response_model=list[DecisionLogRead])
async def list_decision_log(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[DecisionLogRead]:
    return await policy_service.list_decisions(
        db, int(user["org_id"]), start_date=start_date, end_date=end_date, limit=limit,
    )
@router.post("/policy/generate", response_model=list[PolicyRuleRead])
async def generate_policies(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[PolicyRuleRead]:
    """AI-assisted draft policy generation from decision history. All drafts are INACTIVE."""
    org_id = int(user["org_id"])
    drafts = await policy_service.generate_policy_drafts(db, org_id)
    await record_action(
        db,
        event_type="policy_drafts_generated",
        actor_user_id=user["id"],
        organization_id=org_id,
        entity_type="policy_rule",
        entity_id=0,
        payload_json={"drafts_count": len(drafts)},
    )
    return drafts


@router.get("/policies", response_model=list[PolicyRuleRead])
async def list_policies(
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[PolicyRuleRead]:
    return await policy_service.list_policies(db, int(user["org_id"]), active_only=active_only)


@router.post("/policy/activate/{policy_id}", response_model=PolicyRuleRead)
async def activate_policy(
    policy_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> PolicyRuleRead:
    """Activate a draft policy. Requires admin role."""
    org_id = int(user["org_id"])
    policy = await policy_service.activate_policy(db, org_id, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    await record_action(
        db,
        event_type="policy_activated",
        actor_user_id=user["id"],
        organization_id=org_id,
        entity_type="policy_rule",
        entity_id=policy.id,
        payload_json={"title": policy.title},
    )
    return policy
@router.post("/clones/train", response_model=CloneTrainingRunRead)
async def train_clone_brain(
    week_start: date = Query(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> CloneTrainingRunRead:
    org_id = int(user["org_id"])
    result = await clone_brain.train_weekly_clone_scores(
        db,
        organization_id=org_id,
        week_start_date=week_start,
    )
    await record_action(
        db,
        event_type="clone_brain_trained",
        actor_user_id=user["id"],
        organization_id=org_id,
        entity_type="clone_performance_weekly",
        entity_id=None,
        payload_json={"week_start": str(week_start), "employees_scored": result["employees_scored"]},
    )
    return CloneTrainingRunRead(**result)  # type: ignore[arg-type]


@router.get("/clones/scores", response_model=list[CloneScoreRead])
async def list_clone_scores(
    week_start: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[CloneScoreRead]:
    rows = await clone_brain.list_clone_scores(
        db,
        organization_id=int(user["org_id"]),
        week_start_date=week_start,
    )
    return rows


@router.get("/clones/summary", response_model=CloneSummaryRead)
async def clone_score_summary(
    week_start: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> CloneSummaryRead:
    summary = await clone_brain.clone_org_summary(
        db,
        organization_id=int(user["org_id"]),
        week_start_date=week_start,
    )
    return CloneSummaryRead(**summary)  # type: ignore[arg-type]


@router.post("/clones/dispatch-plan", response_model=list[CloneDispatchItemRead])
async def clone_dispatch_plan(
    data: CloneDispatchRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[CloneDispatchItemRead]:
    rows = await clone_brain.build_dispatch_plan(
        db,
        organization_id=int(user["org_id"]),
        challenge=data.challenge,
        week_start_date=data.week_start_date,
        top_n=data.top_n,
    )
    return [CloneDispatchItemRead(**r) for r in rows]


@router.post("/clones/identity-map", response_model=EmployeeIdentityMapRead)
async def upsert_clone_identity_map(
    data: EmployeeIdentityMapUpsert,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EmployeeIdentityMapRead:
    row = await clone_control.upsert_identity_map(
        db,
        organization_id=int(user["org_id"]),
        employee_id=data.employee_id,
        work_email=data.work_email,
        github_login=data.github_login,
        clickup_user_id=data.clickup_user_id,
        slack_user_id=data.slack_user_id,
    )
    return row


@router.get("/clones/identity-map", response_model=list[EmployeeIdentityMapRead])
async def list_clone_identity_maps(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[EmployeeIdentityMapRead]:
    return await clone_control.list_identity_maps(db, organization_id=int(user["org_id"]))


@router.post("/clones/profile", response_model=CloneProfileRead)
async def upsert_clone_profile(
    data: CloneProfileUpsert,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> CloneProfileRead:
    row = await clone_control.upsert_clone_profile(
        db,
        organization_id=int(user["org_id"]),
        employee_id=data.employee_id,
        strengths=data.strengths,
        weak_zones=data.weak_zones,
        preferred_task_types=data.preferred_task_types,
    )
    return CloneProfileRead(**clone_control.profile_to_payload(row))  # type: ignore[arg-type]


@router.get("/clones/profile/{employee_id}", response_model=CloneProfileRead)
async def get_clone_profile(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> CloneProfileRead:
    row = await clone_control.get_clone_profile(
        db,
        organization_id=int(user["org_id"]),
        employee_id=employee_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Clone profile not found")
    return CloneProfileRead(**clone_control.profile_to_payload(row))  # type: ignore[arg-type]


@router.post("/clones/feedback", response_model=dict)
async def record_clone_feedback(
    data: CloneFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    row = await clone_control.record_feedback(
        db,
        organization_id=int(user["org_id"]),
        employee_id=data.employee_id,
        source_type=data.source_type,
        source_id=data.source_id,
        outcome_score=data.outcome_score,
        notes=data.notes,
        created_by=int(user["id"]),
    )
    return {"ok": True, "feedback_id": row.id}


@router.post("/clones/training-plan/generate", response_model=dict)
async def generate_clone_training_plans(
    week_start: date = Query(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    result = await clone_control.generate_role_training_plans(
        db,
        organization_id=int(user["org_id"]),
        week_start_date=week_start,
    )
    return {"ok": True, **result}


@router.get("/clones/training-plan", response_model=list[RoleTrainingPlanRead])
async def list_clone_training_plans(
    week_start: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[RoleTrainingPlanRead]:
    return await clone_control.list_role_training_plans(
        db,
        organization_id=int(user["org_id"]),
        week_start_date=week_start,
    )


@router.patch("/clones/training-plan/{plan_id}", response_model=RoleTrainingPlanRead)
async def update_clone_training_plan_status(
    plan_id: int,
    data: RoleTrainingPlanStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> RoleTrainingPlanRead:
    row = await clone_control.update_role_training_plan_status(
        db,
        organization_id=int(user["org_id"]),
        plan_id=plan_id,
        status=data.status,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Training plan not found")
    return row


# ── API Usage Analytics ───────────────────────────────────────────────────────


@router.get("/api-usage")
async def api_usage_analytics(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """API usage analytics: event counts by type and day."""
    from datetime import timedelta
    from app.models.event import Event

    org_id = int(user["org_id"])
    cutoff = datetime.now(UTC) - timedelta(days=days)

    # Event counts by type
    type_counts = (await db.execute(
        select(Event.event_type, func.count(Event.id))
        .where(Event.organization_id == org_id, Event.created_at >= cutoff)
        .group_by(Event.event_type)
        .order_by(func.count(Event.id).desc())
        .limit(50)
    )).all()

    # Daily totals
    daily_counts = (await db.execute(
        select(func.date(Event.created_at), func.count(Event.id))
        .where(Event.organization_id == org_id, Event.created_at >= cutoff)
        .group_by(func.date(Event.created_at))
        .order_by(func.date(Event.created_at))
    )).all()

    # Top actors
    actor_counts = (await db.execute(
        select(Event.actor_user_id, func.count(Event.id))
        .where(
            Event.organization_id == org_id,
            Event.created_at >= cutoff,
            Event.actor_user_id.isnot(None),
        )
        .group_by(Event.actor_user_id)
        .order_by(func.count(Event.id).desc())
        .limit(10)
    )).all()

    total_events = sum(c for _, c in type_counts)

    return {
        "days": days,
        "total_events": total_events,
        "by_event_type": [
            {"event_type": t, "count": c} for t, c in type_counts
        ],
        "by_day": [
            {"date": str(d), "count": c} for d, c in daily_counts
        ],
        "by_actor": [
            {"actor_user_id": a, "count": c} for a, c in actor_counts
        ],
    }


# ── Team Activity Feed ────────────────────────────────────────────────────────


@router.get("/team-activity")
async def team_activity_feed(
    days: int = Query(3, ge=1, le=30),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """Aggregated team activity feed grouped by user."""
    from datetime import timedelta
    from app.models.event import Event
    from app.models.user import User

    org_id = int(user["org_id"])
    cutoff = datetime.now(UTC) - timedelta(days=days)

    # Recent events with actor info
    events = (await db.execute(
        select(Event)
        .where(Event.organization_id == org_id, Event.created_at >= cutoff)
        .order_by(Event.created_at.desc())
        .limit(limit)
    )).scalars().all()

    # Fetch user names
    user_ids = {e.actor_user_id for e in events if e.actor_user_id}
    user_map: dict[int, str] = {}
    if user_ids:
        users = (await db.execute(
            select(User.id, User.email).where(User.id.in_(user_ids))
        )).all()
        user_map = {u.id: u.email for u in users}

    # Group by actor
    by_actor: dict[int | None, list] = {}
    for e in events:
        key = e.actor_user_id
        if key not in by_actor:
            by_actor[key] = []
        by_actor[key].append({
            "id": e.id,
            "event_type": e.event_type,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    feed = []
    for actor_id, actor_events in by_actor.items():
        feed.append({
            "actor_user_id": actor_id,
            "actor_email": user_map.get(actor_id) if actor_id else None,
            "event_count": len(actor_events),
            "recent_events": actor_events[:20],
        })
    feed.sort(key=lambda x: x["event_count"], reverse=True)

    return {
        "days": days,
        "total_events": len(events),
        "actors": feed,
    }


# ── Soft Delete Restore / Purge ─────────────────────────────────────────────


@router.post("/restore/{entity_type}/{entity_id}", status_code=200)
async def restore_entity(
    entity_type: str,
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Restore a soft-deleted record (contact, task, deal, goal, project)."""
    from app.services.soft_delete import restore
    row = await restore(db, entity_type, entity_id, organization_id=int(user["org_id"]))
    if row is None:
        raise HTTPException(status_code=404, detail="Deleted record not found")
    await record_action(
        db, event_type=f"{entity_type}_restored", actor_user_id=user["id"],
        organization_id=user["org_id"], entity_type=entity_type, entity_id=entity_id,
    )
    return {"restored": True, "entity_type": entity_type, "entity_id": entity_id}


@router.delete("/purge/{entity_type}/{entity_id}", status_code=204)
async def purge_entity(
    entity_type: str,
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO")),
) -> None:
    """Hard-delete a soft-deleted record for GDPR compliance. CEO only."""
    from app.services.soft_delete import purge
    deleted = await purge(db, entity_type, entity_id, organization_id=int(user["org_id"]))
    if not deleted:
        raise HTTPException(status_code=404, detail="Deleted record not found")
    await record_action(
        db, event_type=f"{entity_type}_purged", actor_user_id=user["id"],
        organization_id=user["org_id"], entity_type=entity_type, entity_id=entity_id,
    )
