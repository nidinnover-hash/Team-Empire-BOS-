from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clone_control import EmployeeCloneProfile, EmployeeIdentityMap, RoleTrainingPlan
from app.models.clone_performance import ClonePerformanceWeekly
from app.core.config import settings
from app.models.contact import Contact
from app.models.employee import Employee
from app.models.finance import FinanceEntry
from app.models.memory import DailyContext, TeamMember
from app.models.note import Note
from app.models.task import Task
from app.schemas.layers import (
    AISkillRoutingLayerReport,
    AISkillRoutingMember,
    CloneMarketingSalesLayerReport,
    CloneMarketingSalesMember,
    CloneTrainingLayerReport,
    CloneTrainingMember,
    EmployeeManagementLayerReport,
    EmployeePerformanceLayerReport,
    EmployeePerformanceMember,
    MarketingLayerReport,
    OpportunityAssociationItem,
    OpportunityAssociationLayerReport,
    RevenueManagementLayerReport,
    StaffTrainingLayerReport,
    StaffProsperityLayerReport,
    StudyLayerReport,
    TrainingLayerReport,
)

_MARKETING_TASK_KEYWORDS = ("lead", "follow", "campaign", "outreach", "marketing", "sales")
_AD_SPEND_KEYWORDS = ("ads", "marketing", "campaign", "meta ads", "google ads")
_STUDY_KEYWORDS = ("student", "applicant", "admission", "visa", "ielts", "offer letter", "university")
_TRAINING_KEYWORDS = ("train", "training", "learn", "learning", "course", "cert", "practice", "upskill", "ai")
_RISK_NOTE_KEYWORDS = ("blocked", "struggling", "late", "delay", "help needed")
_AI_NICHE_MAP: dict[str, tuple[str, ...]] = {
    "automation_ops": ("automation", "ops", "workflow", "zapier", "integration"),
    "sales_growth_ai": ("sales", "lead", "outreach", "crm", "conversion"),
    "customer_support_ai": ("support", "service", "ticket", "customer"),
    "content_brand_ai": ("content", "marketing", "social", "brand", "copy"),
    "analytics_strategy_ai": ("analytics", "data", "dashboard", "kpi", "metric"),
}
_OPPORTUNITY_THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "student_admissions_growth": ("student", "admission", "visa", "education", "university"),
    "enterprise_automation": ("automation", "workflow", "integration", "ops"),
    "sales_conversion": ("sales", "lead", "conversion", "outreach"),
    "brand_content_scale": ("content", "marketing", "brand", "social"),
}


def _contains_any(text: str | None, keywords: tuple[str, ...]) -> bool:
    t = (text or "").strip().lower()
    return any(k in t for k in keywords)


async def get_marketing_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> MarketingLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))

    contacts_result = await db.execute(
        select(Contact).where(Contact.organization_id == organization_id)
    )
    contacts = list(contacts_result.scalars().all())
    business_contacts = [c for c in contacts if (c.relationship or "").lower() == "business"]

    new_business_contacts = [
        c for c in business_contacts
        if c.created_at is not None and c.created_at.date() >= since
    ]

    tasks_result = await db.execute(
        select(Task).where(
            Task.organization_id == organization_id,
            Task.is_done.is_(False),
        )
    )
    tasks = list(tasks_result.scalars().all())
    open_follow_up_tasks = [
        t for t in tasks
        if _contains_any(t.title, _MARKETING_TASK_KEYWORDS)
        or _contains_any(t.description, _MARKETING_TASK_KEYWORDS)
        or (t.category or "").lower() in {"business"}
    ]

    finance_result = await db.execute(
        select(FinanceEntry).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.entry_date >= since,
            FinanceEntry.entry_date <= today,
        )
    )
    entries = list(finance_result.scalars().all())
    ad_spend = float(sum(
        e.amount for e in entries
        if e.type == "expense"
        and (_contains_any(e.category, _AD_SPEND_KEYWORDS) or _contains_any(e.description, _AD_SPEND_KEYWORDS))
    ))
    revenue = float(sum(e.amount for e in entries if e.type == "income"))
    spend_to_revenue_ratio = (ad_spend / revenue) if revenue > 0 else (1.0 if ad_spend > 0 else 0.0)

    score = 100
    bottlenecks: list[str] = []
    next_actions: list[str] = []

    if len(new_business_contacts) < 5:
        score -= 20
        bottlenecks.append("Low new business-contact inflow in the selected window.")
        next_actions.append("Increase lead capture cadence and track source quality daily.")
    if len(open_follow_up_tasks) > 12:
        score -= 20
        bottlenecks.append("High follow-up backlog may reduce conversion speed.")
        next_actions.append("Run a 48-hour follow-up sprint and clear old leads first.")
    if ad_spend > 0 and revenue <= 0:
        score -= 30
        bottlenecks.append("Ad spend recorded without income in the same window.")
        next_actions.append("Pause weak campaigns and reallocate spend to proven channels.")
    elif spend_to_revenue_ratio > 0.35:
        score -= 20
        bottlenecks.append("Marketing spend-to-revenue ratio is elevated.")
        next_actions.append("Set weekly ROI thresholds for each campaign.")

    if not next_actions:
        next_actions.append("Maintain current marketing execution and review funnel metrics weekly.")
    score = max(0, min(100, score))

    privacy_guardrails = [
        f"Privacy profile: {settings.PRIVACY_POLICY_PROFILE}",
        f"Response sanitization: {'enabled' if settings.PRIVACY_RESPONSE_SANITIZATION_ENABLED else 'disabled'}",
        f"PII masking: {'enabled' if settings.PRIVACY_MASK_PII else 'disabled'}",
    ]
    legal_guardrails = [
        f"Terms version: {(settings.LEGAL_TERMS_VERSION or 'unset')}",
        f"DPA required: {'yes' if settings.LEGAL_DPA_REQUIRED else 'no'}",
        f"Marketing consent required: {'yes' if settings.LEGAL_MARKETING_CONSENT_REQUIRED else 'no'}",
    ]
    account_guardrails = [
        f"MFA required: {'yes' if settings.ACCOUNT_MFA_REQUIRED else 'no'}",
        f"SSO required: {'yes' if settings.ACCOUNT_SSO_REQUIRED else 'no'}",
        f"Max session hours: {settings.ACCOUNT_SESSION_MAX_HOURS}",
    ]
    risk_signals = 0
    if settings.PRIVACY_POLICY_PROFILE != "strict":
        risk_signals += 1
    if not settings.ACCOUNT_MFA_REQUIRED:
        risk_signals += 1
    if settings.MARKETING_EXPORT_PII_ALLOWED:
        risk_signals += 1
    if not settings.LEGAL_DPA_REQUIRED or not settings.LEGAL_MARKETING_CONSENT_REQUIRED:
        risk_signals += 1
    exposure_risk_level = "LOW" if risk_signals == 0 else ("MEDIUM" if risk_signals <= 2 else "HIGH")

    return MarketingLayerReport(
        window_days=window_days,
        business_contacts_total=len(business_contacts),
        new_business_contacts=len(new_business_contacts),
        open_follow_up_tasks=len(open_follow_up_tasks),
        ad_spend_in_window=ad_spend,
        revenue_in_window=revenue,
        spend_to_revenue_ratio=round(spend_to_revenue_ratio, 4),
        readiness_score=score,
        exposure_risk_level=exposure_risk_level,
        privacy_guardrails=privacy_guardrails,
        legal_guardrails=legal_guardrails,
        account_guardrails=account_guardrails,
        bottlenecks=bottlenecks,
        next_actions=next_actions[:4],
    )


async def get_study_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> StudyLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))

    contacts_result = await db.execute(
        select(Contact).where(Contact.organization_id == organization_id)
    )
    contacts = list(contacts_result.scalars().all())
    study_pipeline_contacts = [
        c for c in contacts
        if _contains_any(c.role, _STUDY_KEYWORDS)
        or _contains_any(c.notes, _STUDY_KEYWORDS)
        or _contains_any(c.company, _STUDY_KEYWORDS)
    ]

    tasks_result = await db.execute(
        select(Task).where(
            Task.organization_id == organization_id,
            Task.is_done.is_(False),
        )
    )
    tasks = list(tasks_result.scalars().all())
    open_study_tasks = [
        t for t in tasks
        if _contains_any(t.title, _STUDY_KEYWORDS) or _contains_any(t.description, _STUDY_KEYWORDS)
    ]
    due_soon_study_tasks = [
        t for t in open_study_tasks
        if t.due_date is not None and t.due_date <= (today + timedelta(days=14))
    ]

    notes_result = await db.execute(
        select(Note).where(
            Note.organization_id == organization_id,
        )
    )
    notes = list(notes_result.scalars().all())
    recent_study_notes = [n for n in notes[:30] if _contains_any(n.content, _STUDY_KEYWORDS)]

    finance_result = await db.execute(
        select(FinanceEntry).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.entry_date >= since,
            FinanceEntry.entry_date <= today,
        )
    )
    entries = list(finance_result.scalars().all())
    study_revenue = float(sum(
        e.amount for e in entries
        if e.type == "income"
        and (_contains_any(e.category, _STUDY_KEYWORDS) or _contains_any(e.description, _STUDY_KEYWORDS))
    ))

    score = 100
    blockers: list[str] = []
    next_actions: list[str] = []

    if len(study_pipeline_contacts) < 5:
        score -= 15
        blockers.append("Study pipeline contact volume appears low.")
        next_actions.append("Audit counselor lead sources and increase weekly intake targets.")
    if len(due_soon_study_tasks) > 8:
        score -= 25
        blockers.append("Many study-related tasks are due soon, increasing deadline risk.")
        next_actions.append("Create a same-day visa/admission deadline triage board.")
    if len(recent_study_notes) < 3:
        score -= 10
        blockers.append("Low recent study operations notes may hide execution gaps.")
        next_actions.append("Capture daily counselor updates into Data Hub > daily_context.")

    if not next_actions:
        next_actions.append("Keep current study operations cadence and monitor deadline queue daily.")
    score = max(0, min(100, score))

    return StudyLayerReport(
        window_days=window_days,
        study_pipeline_contacts=len(study_pipeline_contacts),
        open_study_tasks=len(open_study_tasks),
        due_soon_study_tasks=len(due_soon_study_tasks),
        study_related_revenue=study_revenue,
        operational_score=score,
        blockers=blockers,
        next_actions=next_actions[:4],
    )


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
        )
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
        )
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
    )
    notes = list(notes_result.scalars().all())
    recent_training_notes = [
        n for n in notes[:40]
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


def _member_readiness(member: TeamMember) -> tuple[int, list[str]]:
    risk_flags: list[str] = []
    score = int((member.ai_level or 1) * 18)  # 18..90 baseline by AI maturity

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
        )
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
        )
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
        select(Employee).where(Employee.organization_id == organization_id)
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
        )
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
        )
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
        )
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


async def get_ai_skill_routing_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> AISkillRoutingLayerReport:
    members_result = await db.execute(
        select(TeamMember).where(
            TeamMember.organization_id == organization_id,
            TeamMember.is_active.is_(True),
        )
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
        )
    )
    members = list(members_result.scalars().all())
    active_staff = len(members)
    avg_ai_level = (sum(m.ai_level for m in members) / active_staff) if active_staff else 0.0

    tasks_result = await db.execute(
        select(Task).where(Task.organization_id == organization_id, Task.is_done.is_(False))
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


async def get_clone_training_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> CloneTrainingLayerReport:
    employees_result = await db.execute(
        select(Employee).where(
            Employee.organization_id == organization_id,
            Employee.is_active.is_(True),
        )
    )
    employees = list(employees_result.scalars().all())

    id_map_result = await db.execute(
        select(EmployeeIdentityMap).where(EmployeeIdentityMap.organization_id == organization_id)
    )
    id_maps = list(id_map_result.scalars().all())
    id_by_emp = {row.employee_id: row for row in id_maps}

    profile_result = await db.execute(
        select(EmployeeCloneProfile).where(EmployeeCloneProfile.organization_id == organization_id)
    )
    profiles = list(profile_result.scalars().all())
    profile_by_emp = {row.employee_id: row for row in profiles}

    perf_result = await db.execute(
        select(ClonePerformanceWeekly)
        .where(ClonePerformanceWeekly.organization_id == organization_id)
        .order_by(ClonePerformanceWeekly.week_start_date.desc())
    )
    perf_rows = list(perf_result.scalars().all())
    latest_perf_by_emp: dict[int, ClonePerformanceWeekly] = {}
    for row in perf_rows:
        if row.employee_id not in latest_perf_by_emp:
            latest_perf_by_emp[row.employee_id] = row

    plan_result = await db.execute(
        select(RoleTrainingPlan).where(RoleTrainingPlan.organization_id == organization_id)
    )
    plans = list(plan_result.scalars().all())
    latest_plan_by_emp: dict[int, RoleTrainingPlan] = {}
    open_training_plans = 0
    for row in sorted(plans, key=lambda x: x.week_start_date, reverse=True):
        if row.status == "OPEN":
            open_training_plans += 1
        if row.employee_id not in latest_plan_by_emp:
            latest_plan_by_emp[row.employee_id] = row

    members: list[CloneTrainingMember] = []
    clone_ready_employees = 0
    missing_profile_employees = 0

    for emp in employees:
        has_identity = emp.id in id_by_emp
        has_profile = emp.id in profile_by_emp
        perf = latest_perf_by_emp.get(emp.id)
        score = float(perf.overall_score) if perf else 0.0
        readiness = perf.readiness_level if perf else "developing"
        plan = latest_plan_by_emp.get(emp.id)
        plan_status = (plan.status if plan else "OPEN")
        if has_identity and has_profile:
            clone_ready_employees += 1
        if not has_profile:
            missing_profile_employees += 1
        if not has_identity:
            next_action = "Create identity map (email/GitHub/ClickUp/Slack)."
        elif not has_profile:
            next_action = "Create clone profile with strengths and weak zones."
        elif plan_status == "OPEN":
            next_action = "Complete current role training plan this week."
        else:
            next_action = "Run new weekly clone training plan and feedback loop."
        members.append(
            CloneTrainingMember(
                employee_id=emp.id,
                name=emp.name,
                role=emp.role,
                has_identity_map=has_identity,
                has_clone_profile=has_profile,
                latest_clone_score=round(score, 2),
                readiness_level=readiness,
                training_plan_status=plan_status,
                next_training_action=next_action,
            )
        )

    members.sort(key=lambda x: x.latest_clone_score, reverse=True)

    total = len(employees)
    score = 100
    top_risks: list[str] = []
    next_actions: list[str] = []
    if total == 0:
        score -= 40
        top_risks.append("No active employees found for clone training.")
        next_actions.append("Add employee records and activate clone setup flow.")
    if total > 0 and (missing_profile_employees / total) > 0.25:
        score -= 25
        top_risks.append("Many employees are missing clone profiles.")
        next_actions.append("Run clone profile onboarding sprint for all staff.")
    if total > 0 and (open_training_plans / max(total, 1)) > 0.7:
        score -= 15
        top_risks.append("Too many open training plans indicate execution lag.")
        next_actions.append("Set manager check-ins to close OPEN plans weekly.")
    low_score = len([m for m in members if m.latest_clone_score < 55])
    if total > 0 and low_score > (total // 2):
        score -= 15
        top_risks.append("Majority of clone readiness scores are below target.")
        next_actions.append("Prioritize weak-zone drills and practical role simulations.")
    if not next_actions:
        next_actions.append("Keep weekly clone coaching cadence and feedback discipline.")

    score = max(0, min(100, score))

    return CloneTrainingLayerReport(
        window_days=window_days,
        total_employees=total,
        clone_ready_employees=clone_ready_employees,
        missing_profile_employees=missing_profile_employees,
        open_training_plans=open_training_plans,
        clone_training_score=score,
        top_risks=top_risks[:4],
        next_actions=next_actions[:4],
        members=members[:30],
    )


async def get_clone_marketing_sales_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> CloneMarketingSalesLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))

    contacts_result = await db.execute(select(Contact).where(Contact.organization_id == organization_id))
    contacts = list(contacts_result.scalars().all())
    business_contacts = [c for c in contacts if (c.relationship or "").lower() == "business"]
    new_business_contacts = [
        c for c in business_contacts
        if c.created_at is not None and c.created_at.date() >= since
    ]

    tasks_result = await db.execute(
        select(Task).where(Task.organization_id == organization_id, Task.is_done.is_(False))
    )
    tasks = list(tasks_result.scalars().all())
    follow_up_tasks = [
        t for t in tasks
        if _contains_any(t.title, _MARKETING_TASK_KEYWORDS)
        or _contains_any(t.description, _MARKETING_TASK_KEYWORDS)
        or (t.category or "").lower() == "business"
    ]

    employees_result = await db.execute(
        select(Employee).where(Employee.organization_id == organization_id, Employee.is_active.is_(True))
    )
    employees = list(employees_result.scalars().all())

    perf_result = await db.execute(
        select(ClonePerformanceWeekly)
        .where(ClonePerformanceWeekly.organization_id == organization_id)
        .order_by(ClonePerformanceWeekly.week_start_date.desc())
    )
    perf_rows = list(perf_result.scalars().all())
    latest_perf: dict[int, ClonePerformanceWeekly] = {}
    for row in perf_rows:
        if row.employee_id not in latest_perf:
            latest_perf[row.employee_id] = row

    members: list[CloneMarketingSalesMember] = []
    for emp in employees:
        role_text = (emp.role or "").lower()
        if not any(k in role_text for k in ("sales", "marketing", "growth", "business")):
            continue
        perf = latest_perf.get(emp.id)
        score = float(perf.overall_score) if perf else 0.0
        level = perf.readiness_level if perf else "developing"
        if score >= 75:
            focus = "Enterprise conversion and strategic account expansion"
            action = "Assign high-value lead conversions this week."
        elif score >= 55:
            focus = "Consistent follow-up execution and CRM hygiene"
            action = "Run daily follow-up sprint with conversion tracking."
        else:
            focus = "Foundational outreach script and objection handling"
            action = "Coach with roleplay prompts and 10 lead interactions/day."
        members.append(
            CloneMarketingSalesMember(
                employee_id=emp.id,
                name=emp.name,
                role=emp.role,
                clone_score=round(score, 2),
                readiness_level=level,
                lead_focus=focus,
                next_action=action,
            )
        )

    members.sort(key=lambda x: x.clone_score, reverse=True)

    score = 100
    top_bottlenecks: list[str] = []
    next_actions: list[str] = []
    if len(new_business_contacts) < 5:
        score -= 20
        top_bottlenecks.append("New lead inflow is low for current window.")
        next_actions.append("Increase lead capture channels and daily outreach.")
    if len(follow_up_tasks) > 15:
        score -= 20
        top_bottlenecks.append("Follow-up backlog is high and may hurt conversions.")
        next_actions.append("Clear oldest follow-up tasks within 48 hours.")
    if not members:
        score -= 15
        top_bottlenecks.append("No active marketing/sales employees mapped for clone routing.")
        next_actions.append("Tag employee roles for sales/marketing and build clone profiles.")
    if members and sum(1 for m in members if m.clone_score < 55) > (len(members) // 2):
        score -= 15
        top_bottlenecks.append("Most marketing/sales clones are below readiness target.")
        next_actions.append("Launch weekly clone coaching focused on conversion workflows.")
    if not next_actions:
        next_actions.append("Maintain current marketing-sales rhythm and clone coaching cadence.")

    score = max(0, min(100, score))
    return CloneMarketingSalesLayerReport(
        window_days=window_days,
        business_contacts_total=len(business_contacts),
        new_business_contacts=len(new_business_contacts),
        open_follow_up_tasks=len(follow_up_tasks),
        lead_pipeline_health_score=score,
        top_bottlenecks=top_bottlenecks[:4],
        next_actions=next_actions[:4],
        members=members[:20],
    )


async def get_opportunity_association_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> OpportunityAssociationLayerReport:
    contacts_result = await db.execute(
        select(Contact).where(Contact.organization_id == organization_id)
    )
    contacts = list(contacts_result.scalars().all())
    business_contacts = [c for c in contacts if (c.relationship or "").lower() == "business"]

    employees_result = await db.execute(
        select(Employee).where(
            Employee.organization_id == organization_id,
            Employee.is_active.is_(True),
        )
    )
    employees = list(employees_result.scalars().all())

    def detect_theme(text: str) -> str:
        best_theme = "enterprise_automation"
        best_hits = 0
        for theme, keywords in _OPPORTUNITY_THEME_KEYWORDS.items():
            hits = sum(1 for k in keywords if k in text)
            if hits > best_hits:
                best_theme = theme
                best_hits = hits
        return best_theme

    opportunities: list[OpportunityAssociationItem] = []
    for c in business_contacts[:80]:
        text = " ".join([(c.role or "").lower(), (c.company or "").lower(), (c.notes or "").lower()])
        theme = detect_theme(text)
        best_owner = "CEO"
        best_fit = 45
        reason = "No specialized owner signal detected; route to CEO for triage."
        for e in employees:
            role_text = (e.role or "").lower()
            name_text = (e.name or "").lower()
            fit = 40
            if any(k in role_text for k in _OPPORTUNITY_THEME_KEYWORDS.get(theme, ())):
                fit += 25
            if "sales" in role_text and theme == "sales_conversion":
                fit += 20
            if "marketing" in role_text and theme == "brand_content_scale":
                fit += 20
            if "ops" in role_text and theme == "enterprise_automation":
                fit += 20
            if "counsel" in role_text and theme == "student_admissions_growth":
                fit += 20
            if fit > best_fit:
                best_fit = fit
                best_owner = e.name
                reason = f"{e.name} role aligns with {theme.replace('_', ' ')}."
            if name_text in text:
                best_fit = min(100, fit + 10)
                best_owner = e.name
                reason = f"Contact context references {e.name}, strong ownership fit."
        opportunities.append(
            OpportunityAssociationItem(
                contact_name=c.name,
                company=c.company,
                opportunity_theme=theme,
                fit_score=max(0, min(100, best_fit)),
                recommended_owner=best_owner,
                reasoning=reason,
            )
        )

    opportunities.sort(key=lambda x: x.fit_score, reverse=True)
    top = opportunities[:20]
    high_fit = len([x for x in top if x.fit_score >= 70])
    association_score = max(0, min(100, int(45 + (high_fit * 4))))
    next_actions = [
        "Assign top 5 opportunities to owners with 7-day action plans.",
        "Create follow-up tasks with clear conversion outcomes.",
        "Review opportunity-owner fit in weekly CEO sync.",
    ]
    if not top:
        next_actions = ["Add business contacts and team role data to unlock opportunity association insights."]

    return OpportunityAssociationLayerReport(
        window_days=window_days,
        opportunities_found=len(opportunities),
        association_score=association_score,
        top_opportunities=top,
        next_actions=next_actions,
    )
