"""
Task Engine — AI-powered daily task planning for your team.

Flow:
  1. draft_team_plans()    → AI drafts a task plan for each active team member
  2. Plans sit as "draft" — visible to Nidin, not sent to team
  3. approve_plan()        → Nidin approves a plan
  4. get_team_plans()      → shows all plans for today
"""

from datetime import UTC, date, datetime
from typing import Any, TypedDict, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logs.audit import record_action
from app.models.daily_plan import DailyTaskPlan
from app.models.memory import TeamMember
from app.services.ai_router import call_ai
from app.services.memory import build_memory_context


class TeamPlanResult(TypedDict):
    plan_id: int
    member_name: str
    member_role: str
    member_team: str
    date: str
    status: str
    tasks: list[dict[str, Any]]
    ai_reasoning: str
    approved_at: str | None


# ── Draft Plans ───────────────────────────────────────────────────────────────

async def draft_plan_for_member(
    db: AsyncSession,
    member: TeamMember,
    plan_date: date,
    org_id: int,
    actor_user_id: int,
    memory_context: str = "",
) -> DailyTaskPlan:
    """Draft an AI task plan for one team member."""

    ai_level_label = ["", "no AI skills", "basic AI", "intermediate AI", "advanced AI", "AI expert"][max(0, min(member.ai_level or 0, 5))]

    user_message = (
        f"Create a focused daily task plan for this team member:\n"
        f"Name: {member.name}\n"
        f"Role: {member.role_title or 'Staff'}\n"
        f"Team: {member.team or 'general'}\n"
        f"Skills: {member.skills or 'not specified'}\n"
        f"Current project: {member.current_project or 'none assigned'}\n"
        f"AI skill level: {ai_level_label}\n"
        f"Date: {plan_date}\n\n"
        f"Return EXACTLY 3-5 specific tasks for today. "
        f"Format each task as: TASK: [title] | PRIORITY: [high/medium/low] | DETAILS: [brief description]\n"
        f"Also include one line starting with REASON: explaining why these tasks today."
    )

    system_prompt = (
        "You are Nidin's Tech PM Clone. You assign practical, specific daily tasks to developers.\n"
        "Rules:\n"
        "- Tasks must be completable in one day\n"
        "- Be specific — no vague tasks like 'work on project'\n"
        "- Match the task to the person's skills and current project\n"
        "- If AI level is low, include one AI learning task\n"
        "- Never assign tasks outside their role"
    )

    response = await call_ai(
        system_prompt=system_prompt,
        user_message=user_message,
        memory_context=memory_context,
        organization_id=org_id,
    )

    # Parse AI response into structured tasks
    tasks = []
    reasoning = ""
    for line in response.splitlines():
        line = line.strip()
        if line.startswith("TASK:"):
            parts = line.replace("TASK:", "").split("|")
            task = {
                "title": parts[0].strip() if len(parts) > 0 else line,
                "priority": parts[1].replace("PRIORITY:", "").strip() if len(parts) > 1 else "medium",
                "details": parts[2].replace("DETAILS:", "").strip() if len(parts) > 2 else "",
                "done": False,
            }
            tasks.append(task)
        elif line.startswith("REASON:"):
            reasoning = line.replace("REASON:", "").strip()

    # Fallback if AI didn't follow format
    if not tasks:
        tasks = [{"title": response[:200], "priority": "medium", "details": "", "done": False}]

    plan = DailyTaskPlan(
        organization_id=org_id,
        team_member_id=member.id,
        date=plan_date,
        tasks_json=tasks,
        ai_reasoning=reasoning,
        status="draft",
        created_at=datetime.now(UTC),
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    await record_action(
        db=db,
        event_type="daily_plan_drafted",
        actor_user_id=actor_user_id,
        entity_type="daily_task_plan",
        entity_id=plan.id,
        payload_json={"member": member.name, "date": str(plan_date), "task_count": len(tasks)},
        organization_id=org_id,
    )

    return plan


async def draft_team_plans(
    db: AsyncSession,
    org_id: int,
    actor_user_id: int,
    team: str | None = None,
    plan_date: date | None = None,
) -> list[DailyTaskPlan]:
    """
    Draft AI task plans for all active team members.
    Skips members who already have a plan for today.
    Returns list of newly created draft plans.
    """
    target_date = plan_date or date.today()
    memory_context = await build_memory_context(db, organization_id=org_id)

    # Get active team members
    query = select(TeamMember).where(
        TeamMember.organization_id == org_id,
        TeamMember.is_active.is_(True),
    )
    if team:
        query = query.where(TeamMember.team == team)
    result = await db.execute(query)
    members = list(result.scalars().all())

    # Batch-load all existing plans for this date (single query, not N+1)
    existing_result = await db.execute(
        select(DailyTaskPlan.team_member_id).where(
            DailyTaskPlan.organization_id == org_id,
            DailyTaskPlan.date == target_date,
        )
    )
    existing_member_ids = {row[0] for row in existing_result.all()}

    new_plans = []
    for member in members:
        if member.id in existing_member_ids:
            continue

        plan = await draft_plan_for_member(
            db=db,
            member=member,
            plan_date=target_date,
            org_id=org_id,
            actor_user_id=actor_user_id,
            memory_context=memory_context,
        )
        new_plans.append(plan)

    return new_plans


# ── Get Plans ─────────────────────────────────────────────────────────────────

async def get_team_plans(
    db: AsyncSession,
    org_id: int,
    plan_date: date | None = None,
    status: str | None = None,
) -> list[TeamPlanResult]:
    """
    Get all task plans for a given date, enriched with team member info.
    Returns list of dicts with member name + plan details.
    """
    target_date = plan_date or date.today()

    query = select(DailyTaskPlan).where(
        DailyTaskPlan.organization_id == org_id,
        DailyTaskPlan.date == target_date,
    )
    if status:
        query = query.where(DailyTaskPlan.status == status)
    query = query.order_by(DailyTaskPlan.created_at)

    query = query.outerjoin(TeamMember, TeamMember.id == DailyTaskPlan.team_member_id)
    query = query.add_columns(TeamMember)
    rows = (await db.execute(query)).all()

    enriched: list[TeamPlanResult] = []
    for plan, member in rows:
        enriched.append({
            "plan_id": plan.id,
            "member_name": member.name if member else "Unknown",
            "member_role": member.role_title if member else "",
            "member_team": member.team if member else "",
            "date": str(plan.date),
            "status": plan.status,
            "tasks": plan.tasks_json,
            "ai_reasoning": plan.ai_reasoning,
            "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
        })

    return enriched


async def approve_plan(
    db: AsyncSession,
    plan_id: int,
    org_id: int,
    approver_id: int,
) -> DailyTaskPlan | None:
    """Approve a daily task plan. Status changes from draft → approved."""
    result = await db.execute(
        select(DailyTaskPlan).where(
            DailyTaskPlan.id == plan_id,
            DailyTaskPlan.organization_id == org_id,
        )
    )
    plan = cast(DailyTaskPlan | None, result.scalar_one_or_none())
    if not plan or plan.status != "draft":
        return None

    plan.status = "approved"
    plan.approved_by = approver_id
    plan.approved_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(plan)

    await record_action(
        db=db,
        event_type="daily_plan_approved",
        actor_user_id=approver_id,
        entity_type="daily_task_plan",
        entity_id=plan.id,
        payload_json={"plan_id": plan_id, "date": str(plan.date)},
        organization_id=org_id,
    )
    return plan


async def mark_task_done(
    db: AsyncSession,
    plan_id: int,
    task_index: int,
    org_id: int,
) -> DailyTaskPlan | None:
    """Mark a specific task in a plan as done."""
    result = await db.execute(
        select(DailyTaskPlan).where(
            DailyTaskPlan.id == plan_id,
            DailyTaskPlan.organization_id == org_id,
        )
    )
    plan = cast(DailyTaskPlan | None, result.scalar_one_or_none())
    if not plan:
        return None

    tasks = list(plan.tasks_json)
    if task_index < 0 or task_index >= len(tasks):
        return None

    tasks[task_index]["done"] = True
    plan.tasks_json = tasks
    await db.commit()
    await db.refresh(plan)
    return plan
