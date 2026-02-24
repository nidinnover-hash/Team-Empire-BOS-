from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contact import Contact
from app.models.finance import FinanceEntry
from app.models.memory import DailyContext, TeamMember
from app.models.note import Note
from app.models.task import Task
from app.schemas.layers import (
    EmployeePerformanceLayerReport,
    EmployeePerformanceMember,
    MarketingLayerReport,
    StudyLayerReport,
    TrainingLayerReport,
)

_MARKETING_TASK_KEYWORDS = ("lead", "follow", "campaign", "outreach", "marketing", "sales")
_AD_SPEND_KEYWORDS = ("ads", "marketing", "campaign", "meta ads", "google ads")
_STUDY_KEYWORDS = ("student", "applicant", "admission", "visa", "ielts", "offer letter", "university")
_TRAINING_KEYWORDS = ("train", "training", "learn", "learning", "course", "cert", "practice", "upskill", "ai")
_RISK_NOTE_KEYWORDS = ("blocked", "struggling", "late", "delay", "help needed")


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
