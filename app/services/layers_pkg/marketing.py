"""Marketing and Study layers — lead flow, ad spend, education pipeline."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.contact import Contact
from app.models.finance import FinanceEntry
from app.models.note import Note
from app.models.task import Task
from app.schemas.layers import MarketingLayerReport, StudyLayerReport
from app.services.layers_pkg.helpers import (
    MARKETING_TASK_KEYWORDS,
    PenaltyRule,
    apply_penalties,
    contains_any,
    safe_query,
)

logger = logging.getLogger(__name__)
_AD_SPEND_KEYWORDS = ("ads", "marketing", "campaign", "meta ads", "google ads")
_STUDY_KEYWORDS = ("student", "applicant", "admission", "visa", "ielts", "offer letter", "university")

# ── Penalty rule sets ────────────────────────────────────────────────────────

_MARKETING_PENALTIES: list[PenaltyRule] = [
    (
        lambda ctx: ctx["new_contacts"] < settings.LAYER_MIN_NEW_CONTACTS,
        20,
        "Low new business-contact inflow in the selected window.",
        "Increase lead capture cadence and track source quality daily.",
    ),
    (
        lambda ctx: ctx["follow_ups"] > settings.LAYER_MAX_FOLLOWUP_TASKS,
        20,
        "High follow-up backlog may reduce conversion speed.",
        "Run a 48-hour follow-up sprint and clear old leads first.",
    ),
    (
        lambda ctx: ctx["ad_spend"] > 0 and ctx["revenue"] <= 0,
        30,
        "Ad spend recorded without income in the same window.",
        "Pause weak campaigns and reallocate spend to proven channels.",
    ),
    (
        lambda ctx: ctx["ad_spend"] > 0 and ctx["revenue"] > 0 and ctx["spend_ratio"] > settings.LAYER_SPEND_REVENUE_RATIO,
        20,
        "Marketing spend-to-revenue ratio is elevated.",
        "Set weekly ROI thresholds for each campaign.",
    ),
]

_STUDY_PENALTIES: list[PenaltyRule] = [
    (
        lambda ctx: ctx["pipeline_contacts"] < settings.LAYER_MIN_NEW_CONTACTS,
        15,
        "Study pipeline contact volume appears low.",
        "Audit counselor lead sources and increase weekly intake targets.",
    ),
    (
        lambda ctx: ctx["due_soon"] > 8,
        25,
        "Many study-related tasks are due soon, increasing deadline risk.",
        "Create a same-day visa/admission deadline triage board.",
    ),
    (
        lambda ctx: ctx["recent_notes"] < 3,
        10,
        "Low recent study operations notes may hide execution gaps.",
        "Capture daily counselor updates into Data Hub > daily_context.",
    ),
]


# ── Layer functions ──────────────────────────────────────────────────────────


async def get_marketing_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> MarketingLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))
    ql = settings.LAYER_QUERY_LIMIT

    # Filter business contacts in the DB instead of loading all contacts
    business_contacts = await safe_query(
        db,
        select(Contact).where(
            Contact.organization_id == organization_id,
            Contact.relationship == "business",
        ).limit(ql),
        "marketing:contacts", organization_id,
    )
    new_business_contacts = [
        c for c in business_contacts
        if c.created_at is not None and c.created_at.date() >= since
    ]

    tasks = await safe_query(
        db,
        select(Task).where(
            Task.organization_id == organization_id,
            Task.is_done.is_(False),
        ).limit(ql),
        "marketing:tasks", organization_id,
    )
    open_follow_up_tasks = [
        t for t in tasks
        if contains_any(t.title, MARKETING_TASK_KEYWORDS)
        or contains_any(t.description, MARKETING_TASK_KEYWORDS)
        or (t.category or "").lower() == "business"
    ]

    entries = await safe_query(
        db,
        select(FinanceEntry).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.entry_date >= since,
            FinanceEntry.entry_date <= today,
        ),
        "marketing:finance", organization_id,
    )
    ad_spend = float(sum(
        (e.amount or 0) for e in entries
        if e.type == "expense"
        and (contains_any(e.category, _AD_SPEND_KEYWORDS) or contains_any(e.description, _AD_SPEND_KEYWORDS))
    ))
    revenue = float(sum((e.amount or 0) for e in entries if e.type == "income"))
    spend_to_revenue_ratio = (ad_spend / revenue) if revenue > 0 else (1.0 if ad_spend > 0 else 0.0)

    penalty_ctx = {
        "new_contacts": len(new_business_contacts),
        "follow_ups": len(open_follow_up_tasks),
        "ad_spend": ad_spend,
        "revenue": revenue,
        "spend_ratio": spend_to_revenue_ratio,
    }
    score, bottlenecks, next_actions = apply_penalties(
        _MARKETING_PENALTIES, penalty_ctx,
        "Maintain current marketing execution and review funnel metrics weekly.",
    )

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
        next_actions=next_actions,
    )


async def get_study_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> StudyLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))
    ql = settings.LAYER_QUERY_LIMIT

    contacts = await safe_query(
        db,
        select(Contact).where(Contact.organization_id == organization_id).limit(ql),
        "study:contacts", organization_id,
    )
    study_pipeline_contacts = [
        c for c in contacts
        if contains_any(c.role, _STUDY_KEYWORDS)
        or contains_any(c.notes, _STUDY_KEYWORDS)
        or contains_any(c.company, _STUDY_KEYWORDS)
    ]

    tasks = await safe_query(
        db,
        select(Task).where(
            Task.organization_id == organization_id,
            Task.is_done.is_(False),
        ).limit(ql),
        "study:tasks", organization_id,
    )
    open_study_tasks = [
        t for t in tasks
        if contains_any(t.title, _STUDY_KEYWORDS) or contains_any(t.description, _STUDY_KEYWORDS)
    ]
    due_soon_study_tasks = [
        t for t in open_study_tasks
        if t.due_date is not None and t.due_date <= (today + timedelta(days=14))
    ]

    notes = await safe_query(
        db,
        select(Note).where(
            Note.organization_id == organization_id,
        ).order_by(Note.created_at.desc()).limit(40),
        "study:notes", organization_id,
    )
    recent_study_notes = [n for n in notes if contains_any(n.content, _STUDY_KEYWORDS)]

    entries = await safe_query(
        db,
        select(FinanceEntry).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.entry_date >= since,
            FinanceEntry.entry_date <= today,
        ),
        "study:finance", organization_id,
    )
    study_revenue = float(sum(
        (e.amount or 0) for e in entries
        if e.type == "income"
        and (contains_any(e.category, _STUDY_KEYWORDS) or contains_any(e.description, _STUDY_KEYWORDS))
    ))

    penalty_ctx = {
        "pipeline_contacts": len(study_pipeline_contacts),
        "due_soon": len(due_soon_study_tasks),
        "recent_notes": len(recent_study_notes),
    }
    score, blockers, next_actions = apply_penalties(
        _STUDY_PENALTIES, penalty_ctx,
        "Keep current study operations cadence and monitor deadline queue daily.",
    )

    return StudyLayerReport(
        window_days=window_days,
        study_pipeline_contacts=len(study_pipeline_contacts),
        open_study_tasks=len(open_study_tasks),
        due_soon_study_tasks=len(due_soon_study_tasks),
        study_related_revenue=study_revenue,
        operational_score=score,
        blockers=blockers,
        next_actions=next_actions,
    )
