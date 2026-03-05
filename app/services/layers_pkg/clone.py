"""Clone layers — clone training, clone marketing/sales, opportunity association."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.clone_control import EmployeeCloneProfile, EmployeeIdentityMap, RoleTrainingPlan
from app.models.clone_performance import ClonePerformanceWeekly
from app.models.contact import Contact
from app.models.employee import Employee
from app.models.task import Task
from app.schemas.layers import (
    CloneMarketingSalesLayerReport,
    CloneMarketingSalesMember,
    CloneTrainingLayerReport,
    CloneTrainingMember,
    OpportunityAssociationItem,
    OpportunityAssociationLayerReport,
)
from app.services.layers_pkg.helpers import (
    MARKETING_TASK_KEYWORDS,
    PenaltyRule,
    apply_penalties,
    contains_any,
    latest_by_employee,
    safe_query,
)

logger = logging.getLogger(__name__)
_OPPORTUNITY_THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "student_admissions_growth": ("student", "admission", "visa", "education", "university"),
    "enterprise_automation": ("automation", "workflow", "integration", "ops"),
    "sales_conversion": ("sales", "lead", "conversion", "outreach"),
    "brand_content_scale": ("content", "marketing", "brand", "social"),
}

# ── Penalty rule sets ────────────────────────────────────────────────────────

_TRAINING_PENALTIES: list[PenaltyRule] = [
    (
        lambda ctx: ctx["total"] == 0,
        40,
        "No active employees found for clone training.",
        "Add employee records and activate clone setup flow.",
    ),
    (
        lambda ctx: ctx["total"] > 0 and ctx["missing_ratio"] > 0.25,
        25,
        "Many employees are missing clone profiles.",
        "Run clone profile onboarding sprint for all staff.",
    ),
    (
        lambda ctx: ctx["total"] > 0 and ctx["open_plan_ratio"] > 0.7,
        15,
        "Too many open training plans indicate execution lag.",
        "Set manager check-ins to close OPEN plans weekly.",
    ),
    (
        lambda ctx: ctx["total"] > 0 and ctx["low_score_majority"],
        15,
        "Majority of clone readiness scores are below target.",
        "Prioritize weak-zone drills and practical role simulations.",
    ),
]

_CLONE_MARKETING_PENALTIES: list[PenaltyRule] = [
    (
        lambda ctx: ctx["new_contacts"] < settings.LAYER_MIN_NEW_CONTACTS,
        20,
        "New lead inflow is low for current window.",
        "Increase lead capture channels and daily outreach.",
    ),
    (
        lambda ctx: ctx["follow_ups"] > settings.LAYER_MAX_FOLLOWUP_TASKS,
        20,
        "Follow-up backlog is high and may hurt conversions.",
        "Clear oldest follow-up tasks within 48 hours.",
    ),
    (
        lambda ctx: not ctx["has_members"],
        15,
        "No active marketing/sales employees mapped for clone routing.",
        "Tag employee roles for sales/marketing and build clone profiles.",
    ),
    (
        lambda ctx: ctx["has_members"] and ctx["low_score_majority"],
        15,
        "Most marketing/sales clones are below readiness target.",
        "Launch weekly clone coaching focused on conversion workflows.",
    ),
]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _detect_theme(text: str) -> str:
    """Match text against opportunity theme keywords; 'unclassified' if none match."""
    best_theme = "unclassified"
    best_hits = 0
    for theme, keywords in _OPPORTUNITY_THEME_KEYWORDS.items():
        hits = sum(1 for k in keywords if k in text)
        if hits > best_hits:
            best_theme = theme
            best_hits = hits
    return best_theme


def _build_theme_employee_index(
    employees: list[Employee],
) -> dict[str, list[Employee]]:
    """Precompute theme -> list of employees whose role matches that theme."""
    index: dict[str, list[Employee]] = defaultdict(list)
    for emp in employees:
        role_lower = (emp.job_title or "").lower()
        for theme, keywords in _OPPORTUNITY_THEME_KEYWORDS.items():
            if any(k in role_lower for k in keywords):
                index[theme].append(emp)
        for label in ("sales", "marketing", "ops", "counsel"):
            if label in role_lower:
                index[f"_role_{label}"].append(emp)
    return index


# ── Layer functions ──────────────────────────────────────────────────────────


async def get_clone_training_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> CloneTrainingLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))
    ql = settings.LAYER_QUERY_LIMIT

    employees = await safe_query(
        db,
        select(Employee).where(
            Employee.organization_id == organization_id,
            Employee.is_active.is_(True),
        ).limit(ql),
        "clone_training:employees", organization_id,
    )

    id_maps = await safe_query(
        db,
        select(EmployeeIdentityMap)
        .where(EmployeeIdentityMap.organization_id == organization_id)
        .limit(ql),
        "clone_training:identity_maps", organization_id,
    )
    id_by_emp = {row.employee_id: row for row in id_maps}

    profiles = await safe_query(
        db,
        select(EmployeeCloneProfile)
        .where(EmployeeCloneProfile.organization_id == organization_id)
        .limit(ql),
        "clone_training:profiles", organization_id,
    )
    profile_by_emp = {row.employee_id: row for row in profiles}

    perf_rows = await safe_query(
        db,
        select(ClonePerformanceWeekly)
        .where(ClonePerformanceWeekly.organization_id == organization_id)
        .order_by(ClonePerformanceWeekly.week_start_date.desc())
        .limit(ql),
        "clone_training:perf", organization_id,
    )
    latest_perf_by_emp = latest_by_employee(perf_rows)

    plans = await safe_query(
        db,
        select(RoleTrainingPlan)
        .where(RoleTrainingPlan.organization_id == organization_id)
        .limit(ql),
        "clone_training:plans", organization_id,
    )
    latest_plan_by_emp = latest_by_employee(
        sorted(plans, key=lambda x: x.week_start_date, reverse=True)
    )
    open_training_plans = sum(
        1 for row in latest_plan_by_emp.values()
        if row.status == "OPEN" and row.week_start_date >= since
    )

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
        plan_status = plan.status if plan else "OPEN"
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
                job_title=emp.job_title,
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
    low_score_count = sum(1 for m in members if m.latest_clone_score < 55)
    penalty_ctx = {
        "total": total,
        "missing_ratio": missing_profile_employees / total if total else 0,
        "open_plan_ratio": open_training_plans / max(total, 1),
        "low_score_majority": total > 0 and low_score_count > (total // 2),
    }
    score, top_risks, next_actions = apply_penalties(
        _TRAINING_PENALTIES, penalty_ctx,
        "Keep weekly clone coaching cadence and feedback discipline.",
    )

    return CloneTrainingLayerReport(
        window_days=window_days,
        total_employees=total,
        clone_ready_employees=clone_ready_employees,
        missing_profile_employees=missing_profile_employees,
        open_training_plans=open_training_plans,
        clone_training_score=score,
        top_risks=top_risks,
        next_actions=next_actions,
        members=members[:30],
    )


async def get_clone_marketing_sales_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> CloneMarketingSalesLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))
    ql = settings.LAYER_QUERY_LIMIT

    # Filter business contacts in the DB
    business_contacts = await safe_query(
        db,
        select(Contact).where(
            Contact.organization_id == organization_id,
            Contact.relationship == "business",
        ).limit(ql),
        "clone_mktg:contacts", organization_id,
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
        "clone_mktg:tasks", organization_id,
    )
    follow_up_tasks = [
        t for t in tasks
        if contains_any(t.title, MARKETING_TASK_KEYWORDS)
        or contains_any(t.description, MARKETING_TASK_KEYWORDS)
        or (t.category or "").lower() == "business"
    ]

    employees = await safe_query(
        db,
        select(Employee).where(
            Employee.organization_id == organization_id,
            Employee.is_active.is_(True),
        ).limit(ql),
        "clone_mktg:employees", organization_id,
    )

    perf_rows = await safe_query(
        db,
        select(ClonePerformanceWeekly)
        .where(ClonePerformanceWeekly.organization_id == organization_id)
        .order_by(ClonePerformanceWeekly.week_start_date.desc())
        .limit(ql),
        "clone_mktg:perf", organization_id,
    )
    latest_perf = latest_by_employee(perf_rows)

    members: list[CloneMarketingSalesMember] = []
    for emp in employees:
        role_text = (emp.job_title or "").lower()
        if not any(k in role_text for k in ("sales", "marketing", "growth", "business")):
            continue
        perf = latest_perf.get(emp.id)
        emp_score = float(perf.overall_score) if perf else 0.0
        level = perf.readiness_level if perf else "developing"
        if emp_score >= 75:
            focus = "Enterprise conversion and strategic account expansion"
            action = "Assign high-value lead conversions this week."
        elif emp_score >= 55:
            focus = "Consistent follow-up execution and CRM hygiene"
            action = "Run daily follow-up sprint with conversion tracking."
        else:
            focus = "Foundational outreach script and objection handling"
            action = "Coach with roleplay prompts and 10 lead interactions/day."
        members.append(
            CloneMarketingSalesMember(
                employee_id=emp.id,
                name=emp.name,
                job_title=emp.job_title,
                clone_score=round(emp_score, 2),
                readiness_level=level,
                lead_focus=focus,
                next_action=action,
            )
        )

    members.sort(key=lambda x: x.clone_score, reverse=True)

    penalty_ctx = {
        "new_contacts": len(new_business_contacts),
        "follow_ups": len(follow_up_tasks),
        "has_members": len(members) > 0,
        "low_score_majority": (
            len(members) > 0
            and sum(1 for m in members if m.clone_score < 55) > (len(members) // 2)
        ),
    }
    score, top_bottlenecks, next_actions = apply_penalties(
        _CLONE_MARKETING_PENALTIES, penalty_ctx,
        "Maintain current marketing-sales rhythm and clone coaching cadence.",
    )

    return CloneMarketingSalesLayerReport(
        window_days=window_days,
        business_contacts_total=len(business_contacts),
        new_business_contacts=len(new_business_contacts),
        open_follow_up_tasks=len(follow_up_tasks),
        lead_pipeline_health_score=score,
        top_bottlenecks=top_bottlenecks,
        next_actions=next_actions,
        members=members[:20],
    )


async def get_opportunity_association_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> OpportunityAssociationLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))
    ql = settings.LAYER_QUERY_LIMIT

    # Filter to recent business contacts directly in the DB
    business_contacts = await safe_query(
        db,
        select(Contact).where(
            Contact.organization_id == organization_id,
            Contact.relationship == "business",
            Contact.created_at >= since,
        ).limit(ql),
        "opportunity:contacts", organization_id,
    )

    employees = await safe_query(
        db,
        select(Employee).where(
            Employee.organization_id == organization_id,
            Employee.is_active.is_(True),
        ).limit(ql),
        "opportunity:employees", organization_id,
    )

    # Precompute theme-to-employee index to avoid O(contacts * employees) scanning
    theme_index = _build_theme_employee_index(employees)
    _THEME_ROLE_BONUS: dict[str, str] = {
        "sales_conversion": "_role_sales",
        "brand_content_scale": "_role_marketing",
        "enterprise_automation": "_role_ops",
        "student_admissions_growth": "_role_counsel",
    }

    opportunities: list[OpportunityAssociationItem] = []
    for c in business_contacts[:80]:
        text = " ".join([(c.role or "").lower(), (c.company or "").lower(), (c.notes or "").lower()])
        theme = _detect_theme(text)

        best_owner = "CEO"
        best_fit = 45
        reason = "No specialized owner signal detected; route to CEO for triage."

        # Only check employees relevant to this theme instead of all employees
        candidates: set[int] = set()
        for emp in theme_index.get(theme, []):
            candidates.add(emp.id)
        role_key = _THEME_ROLE_BONUS.get(theme)
        if role_key:
            for emp in theme_index.get(role_key, []):
                candidates.add(emp.id)

        for emp in employees:
            if emp.id not in candidates and (emp.name or "").strip().lower() not in text:
                continue
            role_text = (emp.job_title or "").lower()
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
            name_lower = (emp.name or "").strip().lower()
            if name_lower and name_lower in text:
                fit += 10
                if fit > best_fit:
                    best_fit = min(100, fit)
                    best_owner = emp.name
                    reason = f"Contact context references {emp.name}, strong ownership fit."
            elif fit > best_fit:
                best_fit = fit
                best_owner = emp.name
                reason = f"{emp.name} role aligns with {theme.replace('_', ' ')}."

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
