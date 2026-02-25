"""People layers — training, employee performance, management, revenue, staff, AI routing, prosperity."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.finance import FinanceEntry
from app.models.memory import DailyContext, TeamMember
from app.models.note import Note
from app.models.task import Task
from app.schemas.layers import (
    AISkillRoutingLayerReport,
    AISkillRoutingMember,
    EmployeeManagementLayerReport,
    EmployeePerformanceLayerReport,
    EmployeePerformanceMember,
    RevenueManagementLayerReport,
    StaffProsperityLayerReport,
    StaffTrainingLayerReport,
    TrainingLayerReport,
)

_TRAINING_KEYWORDS = ("train", "training", "learn", "learning", "course", "cert", "practice", "upskill", "ai")
_RISK_NOTE_KEYWORDS = ("blocked", "struggling", "late", "delay", "help needed")
_AI_NICHE_MAP: dict[str, tuple[str, ...]] = {
    "automation_ops": ("automation", "ops", "workflow", "zapier", "integration"),
    "sales_growth_ai": ("sales", "lead", "outreach", "crm", "conversion"),
    "customer_support_ai": ("support", "service", "ticket", "customer"),
    "content_brand_ai": ("content", "marketing", "social", "brand", "copy"),
    "analytics_strategy_ai": ("analytics", "data", "dashboard", "kpi", "metric"),
}


def _contains_any(text: str | None, keywords: tuple[str, ...]) -> bool:
    t = (text or "").strip().lower()
    return any(k in t for k in keywords)


def _member_readiness(member: TeamMember) -> tuple[int, list[str]]:
    risk_flags: list[str] = []
    score = int((member.ai_level or 1) * 18)

    if (member.ai_level or 1) <= 2:
        risk_flags.append("Low AI maturity")
    if not (member.current_project or "").strip():
        risk_flags.append("No current project mapped")
    else:
        score += 5
    if not (member.role_title or "").strip():
        risk_flags.append("Role definition missing")
    else:
        score += 5
    if _contains_any(member.notes, _RISK_NOTE_KEYWORDS):
        risk_flags.append("Risk signal in notes")
        score -= 15

    score = max(0, min(100, score))
    return score, risk_flags


def _detect_niche_for_member(member: TeamMember) -> tuple[str, list[str], float]:
    text = " ".join(
        [
            (member.role_title or "").lower(),
            (member.current_project or "").lower(),
            (member.notes or "").lower(),
            (member.skills or "").lower(),
            (member.team or "").lower(),
        ]
    )
    best_niche = "analytics_strategy_ai"
    best_hits: list[str] = []
    for niche, keywords in _AI_NICHE_MAP.items():
        hits = [k for k in keywords if k in text]
        if len(hits) > len(best_hits):
            best_niche = niche
            best_hits = hits
    confidence = min(1.0, 0.45 + (0.1 * len(best_hits)))
    return best_niche, best_hits[:4], confidence


async def get_training_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> TrainingLayerReport:
    today = date.today()

    members_result = await db.execute(
        select(TeamMember).where(
            TeamMember.organization_id == organization_id,
            TeamMember.is_active.is_(True),
        ).limit(500)
    )
    members = list(members_result.scalars().all())
    active_team_members = len(members)
    avg_ai_level = round(
        (sum(m.ai_level for m in members) / active_team_members) if active_team_members else 0.0,
        2,
    )

    tasks_result = await db.execute(
        select(Task).where(
            Task.organization_id == organization_id,
            Task.is_done.is_(False),
        ).limit(2000)
    )
    tasks = list(tasks_result.scalars().all())
    open_training_tasks = [
        t for t in tasks
        if _contains_any(t.title, _TRAINING_KEYWORDS)
        or _contains_any(t.description, _TRAINING_KEYWORDS)
    ]
    due_soon_training_tasks = [
        t for t in open_training_tasks
        if t.due_date is not None and t.due_date <= (today + timedelta(days=14))
    ]

    notes_result = await db.execute(
        select(Note).where(Note.organization_id == organization_id)
        .order_by(Note.created_at.desc()).limit(40)
    )
    notes = list(notes_result.scalars().all())
    recent_training_notes = [
        n for n in notes
        if _contains_any(n.content, _TRAINING_KEYWORDS)
    ]

    score = 100
    blockers: list[str] = []
    next_actions: list[str] = []

    if active_team_members > 0 and avg_ai_level < 2.5:
        score -= 25
        blockers.append("Average AI skill maturity across the team is below target.")
        next_actions.append("Run weekly hands-on AI workflow training by role.")
    if len(open_training_tasks) < 3:
        score -= 15
        blockers.append("Training task pipeline is too small for continuous capability growth.")
        next_actions.append("Create a recurring training backlog for every team.")
    if len(due_soon_training_tasks) > 10:
        score -= 15
        blockers.append("Too many training tasks are due soon; completion risk is high.")
        next_actions.append("Resequence training tasks into realistic weekly batches.")
    if len(recent_training_notes) < 3:
        score -= 10
        blockers.append("Low recent training notes reduce visibility of team learning progress.")
        next_actions.append("Log key learning outcomes daily in Data Hub.")

    if not next_actions:
        next_actions.append("Maintain current training cadence and track completion weekly.")
    score = max(0, min(100, score))

    return TrainingLayerReport(
        window_days=window_days,
        active_team_members=active_team_members,
        avg_ai_level=avg_ai_level,
        open_training_tasks=len(open_training_tasks),
        due_soon_training_tasks=len(due_soon_training_tasks),
        recent_training_notes=len(recent_training_notes),
        training_score=score,
        blockers=blockers,
        next_actions=next_actions[:4],
    )


async def get_employee_performance_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> EmployeePerformanceLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))

    members_result = await db.execute(
        select(TeamMember).where(
            TeamMember.organization_id == organization_id,
            TeamMember.is_active.is_(True),
        ).limit(500)
    )
    members = list(members_result.scalars().all())
    active_team_members = len(members)
    avg_ai_level = round(
        (sum(m.ai_level for m in members) / active_team_members) if active_team_members else 0.0,
        2,
    )
    low_ai_members = len([m for m in members if (m.ai_level or 1) <= 2])
    high_ai_members = len([m for m in members if (m.ai_level or 1) >= 4])

    tasks_result = await db.execute(
        select(Task).where(
            Task.organization_id == organization_id,
            Task.is_done.is_(False),
        ).limit(2000)
    )
    tasks = list(tasks_result.scalars().all())
    open_operational_tasks = [
        t for t in tasks
        if not _contains_any(t.title, _TRAINING_KEYWORDS)
        and not _contains_any(t.description, _TRAINING_KEYWORDS)
    ]
    overdue_operational_tasks = [
        t for t in open_operational_tasks
        if t.due_date is not None and t.due_date < today
    ]

    blockers_result = await db.execute(
        select(DailyContext).where(
            DailyContext.organization_id == organization_id,
            DailyContext.context_type == "blocker",
            DailyContext.date >= since,
            DailyContext.date <= today,
        )
    )
    blockers = list(blockers_result.scalars().all())

    snapshots: list[EmployeePerformanceMember] = []
    for member in sorted(members, key=lambda m: ((m.team or ""), m.name.lower())):
        readiness_score, risk_flags = _member_readiness(member)
        snapshots.append(
            EmployeePerformanceMember(
                name=member.name,
                team=member.team,
                role_title=member.role_title,
                ai_level=int(member.ai_level or 1),
                readiness_score=readiness_score,
                risk_flags=risk_flags,
            )
        )

    score = 100
    top_risks: list[str] = []
    next_actions: list[str] = []

    if active_team_members == 0:
        score -= 40
        top_risks.append("No active team members configured in memory.")
        next_actions.append("Add your org structure in Memory > Team to unlock performance analytics.")
    if active_team_members > 0 and (low_ai_members / active_team_members) > 0.4:
        score -= 20
        top_risks.append("Large share of team has low AI maturity.")
        next_actions.append("Run role-based AI training for members at level 1-2.")
    if len(overdue_operational_tasks) > max(3, active_team_members):
        score -= 20
        top_risks.append("Operational task backlog is aging past due dates.")
        next_actions.append("Execute a 48-hour overdue-task recovery sprint with daily check-ins.")
    if len(blockers) > max(2, active_team_members // 2):
        score -= 15
        top_risks.append("Blocker event volume is high in the selected window.")
        next_actions.append("Assign explicit blocker owners and enforce same-day resolution updates.")

    if not next_actions:
        next_actions.append("Maintain current execution cadence and review employee score weekly.")
    score = max(0, min(100, score))

    return EmployeePerformanceLayerReport(
        window_days=window_days,
        active_team_members=active_team_members,
        avg_ai_level=avg_ai_level,
        low_ai_members=low_ai_members,
        high_ai_members=high_ai_members,
        open_operational_tasks=len(open_operational_tasks),
        overdue_operational_tasks=len(overdue_operational_tasks),
        blocker_events_in_window=len(blockers),
        performance_score=score,
        top_risks=top_risks[:4],
        next_actions=next_actions[:4],
        members=snapshots[:20],
    )


async def get_employee_management_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> EmployeeManagementLayerReport:
    employees_result = await db.execute(
        select(Employee).where(Employee.organization_id == organization_id).limit(500)
    )
    employees = list(employees_result.scalars().all())
    total_employees = len(employees)
    active_employees = len([e for e in employees if bool(e.is_active)])
    inactive_employees = max(0, total_employees - active_employees)
    github_mapped = len([e for e in employees if (e.github_username or "").strip()])
    clickup_mapped = len([e for e in employees if (e.clickup_user_id or "").strip()])
    unmapped = len(
        [e for e in employees if not (e.github_username or "").strip() and not (e.clickup_user_id or "").strip()]
    )

    tasks_result = await db.execute(
        select(Task).where(
            Task.organization_id == organization_id,
            Task.is_done.is_(False),
        ).limit(2000)
    )
    tasks = list(tasks_result.scalars().all())
    today = date.today()
    open_tasks = len(tasks)
    overdue_tasks = len([t for t in tasks if t.due_date is not None and t.due_date < today])

    score = 100
    top_risks: list[str] = []
    next_actions: list[str] = []

    if active_employees == 0:
        score -= 40
        top_risks.append("No active employees found in employee directory.")
        next_actions.append("Add employee records and mark active team members.")
    if total_employees > 0 and (unmapped / max(total_employees, 1)) > 0.35:
        score -= 20
        top_risks.append("Large share of employees are not mapped to GitHub/ClickUp identities.")
        next_actions.append("Map each employee to GitHub username and ClickUp user ID.")
    if active_employees > 0 and overdue_tasks > active_employees:
        score -= 20
        top_risks.append("Overdue task load exceeds active employee capacity.")
        next_actions.append("Run manager triage to reassign or close stale work items.")
    if total_employees > 0 and github_mapped < max(1, int(total_employees * 0.6)):
        score -= 10
        top_risks.append("GitHub mapping coverage is low.")
        next_actions.append("Enforce GitHub identity mapping for all technical roles.")
    if total_employees > 0 and clickup_mapped < max(1, int(total_employees * 0.6)):
        score -= 10
        top_risks.append("ClickUp mapping coverage is low.")
        next_actions.append("Enforce ClickUp user mapping for operational visibility.")

    if not next_actions:
        next_actions.append("Keep current employee management cadence and review weekly.")
    score = max(0, min(100, score))

    return EmployeeManagementLayerReport(
        window_days=window_days,
        total_employees=total_employees,
        active_employees=active_employees,
        inactive_employees=inactive_employees,
        github_mapped_employees=github_mapped,
        clickup_mapped_employees=clickup_mapped,
        unmapped_employees=unmapped,
        open_tasks=open_tasks,
        overdue_tasks=overdue_tasks,
        management_score=score,
        top_risks=top_risks[:4],
        next_actions=next_actions[:4],
    )


async def get_revenue_management_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> RevenueManagementLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))
    finance_result = await db.execute(
        select(FinanceEntry).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.entry_date >= since,
            FinanceEntry.entry_date <= today,
        )
    )
    entries = list(finance_result.scalars().all())

    income = float(sum(e.amount for e in entries if e.type == "income"))
    expense = float(sum(e.amount for e in entries if e.type == "expense"))
    net = income - expense
    recurring_keywords = ("subscription", "saas", "tool", "license", "retainer")
    recurring_expense = float(
        sum(
            e.amount
            for e in entries
            if e.type == "expense"
            and (_contains_any(e.category, recurring_keywords) or _contains_any(e.description, recurring_keywords))
        )
    )
    recurring_ratio = (recurring_expense / expense) if expense > 0 else 0.0

    score = 100
    top_risks: list[str] = []
    next_actions: list[str] = []
    if income <= 0:
        score -= 35
        top_risks.append("No income recorded in selected window.")
        next_actions.append("Verify invoicing and revenue capture pipeline.")
    if net < 0:
        score -= 30
        top_risks.append("Net revenue is negative for selected window.")
        next_actions.append("Cut low-ROI spend and prioritize high-conversion channels.")
    if recurring_ratio > 0.55:
        score -= 15
        top_risks.append("Recurring expense ratio is high.")
        next_actions.append("Run SaaS/license audit and remove underused tools.")
    if expense > income * 0.8 and income > 0:
        score -= 10
        top_risks.append("Expense-to-income ratio is approaching unhealthy range.")
        next_actions.append("Set weekly budget guardrails per cost center.")
    if not next_actions:
        next_actions.append("Maintain current revenue discipline and monitor weekly cash flow.")
    score = max(0, min(100, score))

    return RevenueManagementLayerReport(
        window_days=window_days,
        income_in_window=income,
        expense_in_window=expense,
        net_in_window=net,
        recurring_expense_ratio=round(recurring_ratio, 4),
        revenue_health_score=score,
        top_risks=top_risks[:4],
        next_actions=next_actions[:4],
    )


async def get_staff_training_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> StaffTrainingLayerReport:
    today = date.today()
    members_result = await db.execute(
        select(TeamMember).where(
            TeamMember.organization_id == organization_id,
            TeamMember.is_active.is_(True),
        ).limit(500)
    )
    members = list(members_result.scalars().all())
    active_staff = len(members)
    avg_ai_level = round(
        (sum(m.ai_level for m in members) / active_staff) if active_staff else 0.0,
        2,
    )
    low_ai = len([m for m in members if (m.ai_level or 1) <= 2])

    tasks_result = await db.execute(
        select(Task).where(
            Task.organization_id == organization_id,
            Task.is_done.is_(False),
        ).limit(2000)
    )
    tasks = list(tasks_result.scalars().all())
    open_training_tasks = [
        t for t in tasks
        if _contains_any(t.title, _TRAINING_KEYWORDS)
        or _contains_any(t.description, _TRAINING_KEYWORDS)
    ]
    due_soon_training_tasks = [
        t for t in open_training_tasks
        if t.due_date is not None and t.due_date <= (today + timedelta(days=14))
    ]

    score = 100
    top_risks: list[str] = []
    next_actions: list[str] = []
    if active_staff == 0:
        score -= 40
        top_risks.append("No active staff entries in team memory.")
        next_actions.append("Add active staff to memory/team for training governance.")
    if active_staff > 0 and avg_ai_level < 2.5:
        score -= 25
        top_risks.append("Average AI maturity of staff is below target.")
        next_actions.append("Run role-based weekly AI training sprint.")
    if len(open_training_tasks) < max(3, active_staff):
        score -= 15
        top_risks.append("Training backlog is too small to sustain upskilling.")
        next_actions.append("Create training backlog per staff role.")
    if len(due_soon_training_tasks) > max(4, active_staff):
        score -= 10
        top_risks.append("Too many training tasks due soon can reduce completion quality.")
        next_actions.append("Re-sequence due dates and assign staff owners clearly.")
    if not next_actions:
        next_actions.append("Maintain training cadence and audit staff progress weekly.")
    score = max(0, min(100, score))

    return StaffTrainingLayerReport(
        window_days=window_days,
        active_staff=active_staff,
        avg_ai_level=avg_ai_level,
        low_ai_level_staff=low_ai,
        open_training_tasks=len(open_training_tasks),
        due_soon_training_tasks=len(due_soon_training_tasks),
        training_velocity_score=score,
        top_risks=top_risks[:4],
        next_actions=next_actions[:4],
    )


async def get_ai_skill_routing_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> AISkillRoutingLayerReport:
    members_result = await db.execute(
        select(TeamMember).where(
            TeamMember.organization_id == organization_id,
            TeamMember.is_active.is_(True),
        ).limit(500)
    )
    members = list(members_result.scalars().all())
    active_staff = len(members)
    avg_ai_level = round(
        (sum(m.ai_level for m in members) / active_staff) if active_staff else 0.0,
        2,
    )

    routed: list[AISkillRoutingMember] = []
    niche_counts: dict[str, int] = {}
    for member in members:
        niche, signals, confidence = _detect_niche_for_member(member)
        niche_counts[niche] = niche_counts.get(niche, 0) + 1
        readiness_score = max(0, min(100, int((member.ai_level or 1) * 18 + (10 if signals else 0))))
        routed.append(
            AISkillRoutingMember(
                name=member.name,
                role_title=member.role_title,
                ai_level=int(member.ai_level or 1),
                recommended_niche=niche,
                interest_signals=signals,
                readiness_score=readiness_score,
                confidence=round(confidence, 2),
                next_step=f"Assign one {niche} mini-project this week with measurable output.",
            )
        )
    routed.sort(key=lambda m: (m.readiness_score, m.confidence), reverse=True)

    top_opportunities = [
        f"Scale {niche.replace('_', ' ')} with {count} aligned team members."
        for niche, count in sorted(niche_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    ]
    routing_score = max(0, min(100, int(40 + (avg_ai_level * 12) + (len(top_opportunities) * 8))))
    next_actions = [
        "Route each employee into one niche AI track and assign a weekly output target.",
        "Pair low-AI-level staff with high-readiness peers for hands-on mentorship.",
        "Review niche outcomes in weekly CEO execution meeting.",
    ]
    if not top_opportunities:
        top_opportunities = ["Add staff profiles/notes to unlock niche routing signals."]

    return AISkillRoutingLayerReport(
        window_days=window_days,
        active_staff=active_staff,
        avg_ai_level=avg_ai_level,
        routing_score=routing_score,
        top_opportunities=top_opportunities,
        members=routed[:30],
        next_actions=next_actions,
    )


async def get_staff_prosperity_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> StaffProsperityLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))

    members_result = await db.execute(
        select(TeamMember).where(
            TeamMember.organization_id == organization_id,
            TeamMember.is_active.is_(True),
        ).limit(500)
    )
    members = list(members_result.scalars().all())
    active_staff = len(members)
    avg_ai_level = (sum(m.ai_level for m in members) / active_staff) if active_staff else 0.0

    tasks_result = await db.execute(
        select(Task).where(Task.organization_id == organization_id, Task.is_done.is_(False)).limit(2000)
    )
    tasks = list(tasks_result.scalars().all())
    overdue = len([t for t in tasks if t.due_date is not None and t.due_date < today])

    finance_result = await db.execute(
        select(FinanceEntry).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.entry_date >= since,
            FinanceEntry.entry_date <= today,
        )
    )
    entries = list(finance_result.scalars().all())
    income = float(sum(e.amount for e in entries if e.type == "income"))
    expense = float(sum(e.amount for e in entries if e.type == "expense"))
    net = income - expense

    opportunity_index = max(0, min(100, int(45 + avg_ai_level * 10 - overdue * 2)))
    wealth_index = max(0, min(100, int(50 + (15 if net > 0 else -15))))
    happiness_index = max(0, min(100, int(70 - overdue * 3)))
    freedom_index = max(0, min(100, int(40 + avg_ai_level * 8 - overdue * 2)))
    composite = int((opportunity_index + wealth_index + happiness_index + freedom_index) / 4)

    top_risks: list[str] = []
    next_actions: list[str] = []
    if overdue > max(2, active_staff):
        top_risks.append("Overdue workload may reduce team happiness and autonomy.")
        next_actions.append("Run a 48-hour workload reset and remove low-value tasks.")
    if net <= 0:
        top_risks.append("Net financial performance is not supporting growth incentives.")
        next_actions.append("Improve conversion and reduce non-essential spend immediately.")
    if avg_ai_level < 2.5 and active_staff > 0:
        top_risks.append("AI maturity gap is limiting opportunity and freedom.")
        next_actions.append("Launch role-based AI coaching for all teams this week.")
    if not next_actions:
        next_actions.append("Maintain current growth rhythm and keep weekly reflection discipline.")

    ceo_message = (
        "Lead with love and clarity: grow people capability weekly, remove friction daily, "
        "and convert gains into freedom for every team."
    )

    return StaffProsperityLayerReport(
        window_days=window_days,
        active_staff=active_staff,
        opportunity_index=opportunity_index,
        wealth_index=wealth_index,
        happiness_index=happiness_index,
        freedom_index=freedom_index,
        composite_score=composite,
        top_risks=top_risks[:4],
        next_actions=next_actions[:4],
        ceo_message=ceo_message,
    )
