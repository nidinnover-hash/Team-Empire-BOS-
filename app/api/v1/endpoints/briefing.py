from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.briefing import (
    ApprovePlanResponse,
    CompleteTaskResponse,
    DailyBriefingResponse,
    DraftPlansResponse,
    ExecutiveBriefingResponse,
    TeamDashboardResponse,
    TeamPlanRead,
)
from app.services.briefing import (
    get_daily_briefing,
    get_executive_briefing,
    get_team_dashboard,
)
from app.services.task_engine import (
    approve_plan,
    draft_team_plans,
    get_team_plans,
    mark_task_done,
)

router = APIRouter(prefix="/briefing", tags=["Briefing & Task Plans"])


# ── Daily Briefing ────────────────────────────────────────────────────────────

@router.get("/today", response_model=DailyBriefingResponse)
async def daily_briefing(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DailyBriefingResponse:
    """
    AI-generated morning briefing for Nidin.
    Covers team status, urgent actions, and today's focus.
    """
    org_id = int(current_user["org_id"])
    payload = await get_daily_briefing(
        db=db,
        org_id=org_id,
        actor_user_id=int(current_user["id"]),
        actor_role=str(current_user["role"]),
    )
    return DailyBriefingResponse.model_validate(payload)


# ── Team Dashboard ────────────────────────────────────────────────────────────

@router.get("/team", response_model=TeamDashboardResponse)
async def team_dashboard(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> TeamDashboardResponse:
    """
    Live team dashboard — all members, their plans, tasks done vs pending.
    No AI call, always fast.
    """
    org_id = int(_user["org_id"])
    payload = await get_team_dashboard(db=db, org_id=org_id)
    return TeamDashboardResponse.model_validate(payload)


@router.get("/executive", response_model=ExecutiveBriefingResponse)
async def executive_briefing(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ExecutiveBriefingResponse:
    """
    Executive dashboard snapshot: team, approvals, inbox, and today's priorities.
    Non-AI and safe to call frequently.
    """
    org_id = int(_user["org_id"])
    payload = await get_executive_briefing(db=db, org_id=org_id)
    return ExecutiveBriefingResponse.model_validate(payload)


# ── Daily Task Plans ──────────────────────────────────────────────────────────

@router.post("/plans/draft", response_model=DraftPlansResponse)
async def draft_plans(
    team: str | None = None,
    plan_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DraftPlansResponse:
    """
    AI drafts a daily task plan for each active team member.
    Plans are created as drafts — nothing is sent until approved.
    Filter by team name (tech, sales, ops) or leave empty for all.
    """
    org_id = int(current_user["org_id"])
    plans = await draft_team_plans(
        db=db,
        org_id=org_id,
        actor_user_id=int(current_user["id"]),
        actor_role=str(current_user["role"]),
        team=team,
        plan_date=plan_date,
    )
    return DraftPlansResponse(
        drafted=len(plans),
        message=f"{len(plans)} plan(s) drafted. Review at GET /briefing/plans",
        plan_ids=[p.id for p in plans],
    )


@router.get("/plans", response_model=list[TeamPlanRead])
async def list_plans(
    plan_date: date | None = None,
    status: Literal["draft", "approved", "sent"] | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[TeamPlanRead]:
    """
    List all task plans for today (or a specific date).
    Filter by status: draft, approved, sent.
    """
    org_id = int(_user["org_id"])
    plans = await get_team_plans(db=db, org_id=org_id, plan_date=plan_date, status=status)
    return [TeamPlanRead.model_validate(item) for item in plans]


@router.post("/plans/{plan_id}/approve", response_model=ApprovePlanResponse)
async def approve_task_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ApprovePlanResponse:
    """
    Approve a drafted task plan. CEO/ADMIN only.
    After approval the plan is locked and ready to be communicated to the team member.
    """
    org_id = int(current_user["org_id"])
    plan = await approve_plan(
        db=db,
        plan_id=plan_id,
        org_id=org_id,
        approver_id=int(current_user["id"]),
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found or already approved")
    return ApprovePlanResponse(
        plan_id=plan_id,
        status="approved",
        approved_at=plan.approved_at.isoformat() if plan.approved_at else "",
    )


@router.post("/plans/{plan_id}/tasks/{task_index}/done", response_model=CompleteTaskResponse)
async def complete_task(
    plan_id: int,
    task_index: int,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> CompleteTaskResponse:
    """Mark a specific task in a plan as done. Zero-indexed."""
    org_id = int(_user["org_id"])
    plan = await mark_task_done(db=db, plan_id=plan_id, task_index=task_index, org_id=org_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan or task not found")
    done_count = sum(1 for t in plan.tasks_json if t.get("done"))
    return CompleteTaskResponse(
        plan_id=plan_id,
        task_index=task_index,
        marked_done=True,
        progress=f"{done_count}/{len(plan.tasks_json)} tasks done",
    )
