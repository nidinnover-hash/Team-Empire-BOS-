"""Marketing and Study layers — lead flow, ad spend, education pipeline."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contact import Contact
from app.models.finance import FinanceEntry
from app.models.note import Note
from app.models.task import Task
from app.schemas.layers import MarketingLayerReport, StudyLayerReport

_MARKETING_TASK_KEYWORDS = ("lead", "follow", "campaign", "outreach", "marketing", "sales")
_AD_SPEND_KEYWORDS = ("ads", "marketing", "campaign", "meta ads", "google ads")
_STUDY_KEYWORDS = ("student", "applicant", "admission", "visa", "ielts", "offer letter", "university")


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
        select(Contact).where(Contact.organization_id == organization_id).limit(1000)
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
        ).limit(1000)
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
        select(Contact).where(Contact.organization_id == organization_id).limit(1000)
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
        ).limit(2000)
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
        ).order_by(Note.created_at.desc()).limit(40)
    )
    notes = list(notes_result.scalars().all())
    recent_study_notes = [n for n in notes if _contains_any(n.content, _STUDY_KEYWORDS)]

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
