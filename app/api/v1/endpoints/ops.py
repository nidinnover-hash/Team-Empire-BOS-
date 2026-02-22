from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.privacy import sanitize_response_payload
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.models.approval import Approval
from app.schemas.daily_run import DailyRunRead
from app.schemas.event import EventRead
from app.schemas.project import ProjectCreate, ProjectRead, ProjectStatusUpdate
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services import briefing as briefing_service
from app.services import daily_run as daily_run_service
from app.services import email_service
from app.services import event as event_service
from app.services import project as project_service
from app.services import task as task_service
from app.services import task_engine

router = APIRouter(prefix="/ops", tags=["Ops"])


async def run_daily_run_workflow(
    db: AsyncSession,
    org_id: int,
    actor_user_id: int,
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

        await record_action(
            db=db,
            event_type="daily_run_drafted",
            actor_user_id=actor_user_id,
            organization_id=org_id,
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
    except Exception:
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
        except Exception:
            pass  # Don't shadow the original exception
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
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
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
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
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


@router.post("/daily-run")
async def daily_run_ops(
    draft_email_limit: int = Query(5, ge=0, le=20),
    team: str | None = Query(None),
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
    return await run_daily_run_workflow(
        db=db,
        org_id=int(user["org_id"]),
        actor_user_id=int(user["id"]),
        draft_email_limit=draft_email_limit,
        team=team,
    )


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
