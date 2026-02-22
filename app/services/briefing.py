"""
Briefing service — daily morning summary and team dashboard data.

Two functions:
  get_team_dashboard()  → structured team status (no AI needed)
  get_daily_briefing()  → AI-generated morning summary for Nidin
"""

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.daily_plan import DailyTaskPlan
from app.models.email import Email
from app.models.memory import TeamMember
from app.services.ai_router import call_ai
from app.services.calendar_service import get_calendar_events_from_context
from app.services.memory import build_memory_context, get_daily_context


# ── Team Dashboard ────────────────────────────────────────────────────────────

async def get_team_dashboard(db: AsyncSession, org_id: int) -> dict:
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

    team_data = []
    total_tasks_today = 0
    total_done = 0
    members_without_plan = []

    for member in members:
        # Get today's plan for this member
        plan_result = await db.execute(
            select(DailyTaskPlan).where(
                DailyTaskPlan.organization_id == org_id,
                DailyTaskPlan.team_member_id == member.id,
                DailyTaskPlan.date == today,
            )
        )
        plan = plan_result.scalar_one_or_none()

        tasks = plan.tasks_json if plan else []
        done_count = sum(1 for t in tasks if t.get("done"))
        total_tasks_today += len(tasks)
        total_done += done_count

        if not plan:
            members_without_plan.append(member.name)

        ai_label = ["", "No AI", "Basic AI", "Intermediate AI", "Advanced AI", "AI Expert"][member.ai_level]

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
            Email.is_read == False,  # noqa: E712
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
) -> dict:
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

    members_without_plan = dashboard["summary"]["members_without_plan"]
    no_plan_text = ", ".join(members_without_plan) if members_without_plan else "All members have plans"

    user_message = f"""
Generate my morning briefing for {today}.

TEAM STATUS:
- {dashboard['summary']['total_members']} active team members
- {dashboard['summary']['members_with_plan']} have task plans today
- No plan yet: {no_plan_text}
- Total tasks today: {dashboard['summary']['total_tasks_today']}
- Pending approvals waiting for me: {dashboard['summary']['pending_approvals']}
- Unread emails: {dashboard['summary']['unread_emails']}

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
    )

    return {
        "date": str(today),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "briefing": briefing_text,
        "raw_data": dashboard["summary"],
    }


async def get_executive_briefing(
    db: AsyncSession,
    org_id: int,
) -> dict:
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
            Email.is_read == False,  # noqa: E712
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
