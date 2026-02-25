"""
Briefing service — daily morning summary and team dashboard data.

Two functions:
  get_team_dashboard()  → structured team status (no AI needed)
  get_daily_briefing()  → AI-generated morning summary for Nidin
"""

from datetime import date, datetime, timezone
from typing import Any, TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.daily_plan import DailyTaskPlan
from app.models.email import Email
from app.models.memory import TeamMember
from app.services.ai_router import call_ai
from app.services.calendar_service import get_calendar_events_from_context
from app.services.memory import build_memory_context, get_daily_context

_AI_LEVEL_LABELS = [
    "",
    "No AI",
    "Basic AI",
    "Intermediate AI",
    "Advanced AI",
    "AI Expert",
]


class TeamDashboardSummary(TypedDict):
    total_members: int
    members_with_plan: int
    members_without_plan: list[str]
    total_tasks_today: int
    tasks_done: int
    tasks_pending: int
    pending_approvals: int
    unread_emails: int


class TeamDashboardResult(TypedDict):
    date: str
    summary: TeamDashboardSummary
    team: list[dict[str, Any]]


class DailyBriefingResult(TypedDict):
    date: str
    generated_at: str
    briefing: str
    raw_data: TeamDashboardSummary


class ExecutiveBriefingResult(TypedDict):
    date: str
    generated_at: str
    summary: TeamDashboardSummary
    team_summary: TeamDashboardSummary
    calendar: dict[str, Any]
    approvals: dict[str, Any]
    inbox: dict[str, Any]
    today_priorities: list[str]


def _ai_level_label(level: int | None) -> str:
    """Normalize an AI level score to a bounded human-readable label."""
    return _AI_LEVEL_LABELS[max(0, min(level or 0, 5))]


# ── Team Dashboard ────────────────────────────────────────────────────────────

async def get_team_dashboard(db: AsyncSession, org_id: int) -> TeamDashboardResult:
    """
    Returns a structured snapshot of your entire team right now.
    No AI call — pure data. Fast and always accurate.
    """
    today = date.today()

    # Get all active team members
    members_result = await db.execute(
        select(TeamMember)
        .where(
            TeamMember.organization_id == org_id,
            TeamMember.is_active.is_(True),
        )
        .order_by(TeamMember.team, TeamMember.name)
    )
    members = list(members_result.scalars().all())

    # Batch-fetch all plans for today in one query (avoids N+1)
    plans_result = await db.execute(
        select(DailyTaskPlan).where(
            DailyTaskPlan.organization_id == org_id,
            DailyTaskPlan.date == today,
        )
    )
    plans_by_member: dict[int, DailyTaskPlan] = {
        p.team_member_id: p for p in plans_result.scalars().all()
    }

    team_data: list[dict] = []
    total_tasks_today = 0
    total_done = 0
    members_without_plan: list[str] = []

    for member in members:
        plan = plans_by_member.get(member.id)

        tasks = plan.tasks_json if plan else []
        done_count = sum(1 for t in tasks if t.get("done"))
        total_tasks_today += len(tasks)
        total_done += done_count

        if not plan:
            members_without_plan.append(member.name)

        ai_label = _ai_level_label(member.ai_level)

        team_data.append({
            "id": member.id,
            "name": member.name,
            "role": member.role_title,
            "team": member.team,
            "ai_level": ai_label,
            "current_project": member.current_project,
            "today": {
                "plan_status": plan.status if plan else "no_plan",
                "total_tasks": len(tasks),
                "done": done_count,
                "pending": len(tasks) - done_count,
                "tasks": tasks,
            },
        })

    # Pending approvals count
    approvals_result = await db.execute(
        select(func.count()).where(
            Approval.organization_id == org_id,
            Approval.status == "pending",
        )
    )
    pending_approvals = approvals_result.scalar() or 0

    # Unread emails count
    emails_result = await db.execute(
        select(func.count()).where(
            Email.organization_id == org_id,
            Email.is_read.is_(False),
        )
    )
    unread_emails = emails_result.scalar() or 0

    return {
        "date": str(today),
        "summary": {
            "total_members": len(members),
            "members_with_plan": len(members) - len(members_without_plan),
            "members_without_plan": members_without_plan,
            "total_tasks_today": total_tasks_today,
            "tasks_done": total_done,
            "tasks_pending": total_tasks_today - total_done,
            "pending_approvals": pending_approvals,
            "unread_emails": unread_emails,
        },
        "team": team_data,
    }


# ── Daily Briefing ────────────────────────────────────────────────────────────

async def get_daily_briefing(
    db: AsyncSession,
    org_id: int,
    actor_user_id: int,
) -> DailyBriefingResult:
    """
    AI-generated morning briefing for Nidin.
    Combines team status + pending actions + today's context into one summary.
    """
    today = date.today()

    # Gather all data
    dashboard = await get_team_dashboard(db, org_id)
    today_context = await get_daily_context(db, organization_id=org_id, for_date=today)
    calendar_events = await get_calendar_events_from_context(db, organization_id=org_id, for_date=today)
    memory_context = await build_memory_context(db, organization_id=org_id)

    # Build a data summary to feed the AI
    context_items = "\n".join(
        f"  [{c.context_type.upper()}] {c.content}" + (f" (re: {c.related_to})" if c.related_to else "")
        for c in today_context
        if c.context_type != "calendar_event"
    ) or "  None added yet."

    calendar_lines = "\n".join(
        f"  - {e.content}" for e in calendar_events
    ) or "  No calendar events synced for today."

    summary = dashboard["summary"]
    members_without_plan = summary["members_without_plan"]
    no_plan_text = ", ".join(members_without_plan) if members_without_plan else "All members have plans"

    user_message = f"""
Generate my morning briefing for {today}.

TEAM STATUS:
- {summary['total_members']} active team members
- {summary['members_with_plan']} have task plans today
- No plan yet: {no_plan_text}
- Total tasks today: {summary['total_tasks_today']}
- Pending approvals waiting for me: {summary['pending_approvals']}
- Unread emails: {summary['unread_emails']}

TODAY'S CONTEXT:
{context_items}

TODAY'S CALENDAR:
{calendar_lines}

Write a sharp, direct morning briefing. Structure it as:
1. SITUATION (2 sentences max — what's the state of the team today)
2. URGENT (what needs my attention first)
3. CALENDAR (key meetings/events to prepare for)
4. WATCH (what could become a problem)
5. FOCUS (my #1 priority today as CEO)
"""

    briefing_text = await call_ai(
        system_prompt=(
            "You are Nidin's CEO Clone. Generate a concise, honest morning briefing.\n"
            "Be direct. No fluff. Treat Nidin like the CEO he is.\n"
            "If something looks wrong or missing, say it clearly."
        ),
        user_message=user_message,
        memory_context=memory_context,
        organization_id=org_id,
    )

    return {
        "date": str(today),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "briefing": briefing_text,
        "raw_data": summary,
    }


async def get_executive_briefing(
    db: AsyncSession,
    org_id: int,
) -> ExecutiveBriefingResult:
    """
    Executive snapshot for dashboard cards.
    Fast, structured, and non-AI for reliability.
    """
    today = date.today()
    dashboard = await get_team_dashboard(db, org_id)
    today_context = await get_daily_context(db, organization_id=org_id, for_date=today)
    calendar_events = await get_calendar_events_from_context(db, organization_id=org_id, for_date=today)

    approvals_result = await db.execute(
        select(Approval)
        .where(Approval.organization_id == org_id)
        .order_by(Approval.created_at.desc())
        .limit(10)
    )
    recent_approvals = list(approvals_result.scalars().all())

    unread_result = await db.execute(
        select(Email)
        .where(
            Email.organization_id == org_id,
            Email.is_read.is_(False),
        )
        .order_by(Email.received_at.desc())
        .limit(10)
    )
    unread_emails = list(unread_result.scalars().all())

    priorities = [
        c.content
        for c in today_context
        if (c.context_type or "").strip().lower() == "priority"
    ]
    if not priorities:
        priorities = [c.content for c in today_context[:3]]

    return {
        "date": str(today),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # Keep both keys for backward compatibility with scheduler/API clients.
        "summary": dashboard["summary"],
        "team_summary": dashboard["summary"],
        "calendar": {
            "event_count": len(calendar_events),
            "events": [{"content": e.content, "location": e.related_to} for e in calendar_events],
        },
        "approvals": {
            "pending_count": dashboard["summary"]["pending_approvals"],
            "recent": [
                {
                    "id": a.id,
                    "approval_type": a.approval_type,
                    "status": a.status,
                    "requested_by": a.requested_by,
                    "approved_by": a.approved_by,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "approved_at": a.approved_at.isoformat() if a.approved_at else None,
                }
                for a in recent_approvals
            ],
        },
        "inbox": {
            "unread_count": dashboard["summary"]["unread_emails"],
            "recent_unread": [
                {
                    "id": e.id,
                    "from": e.from_address,
                    "subject": e.subject,
                    "received_at": e.received_at.isoformat() if e.received_at else None,
                }
                for e in unread_emails
            ],
        },
        "today_priorities": priorities,
    }
