"""Clone layers — clone training, clone marketing/sales, opportunity association."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

_MARKETING_TASK_KEYWORDS = ("lead", "follow", "campaign", "outreach", "marketing", "sales")
_OPPORTUNITY_THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "student_admissions_growth": ("student", "admission", "visa", "education", "university"),
    "enterprise_automation": ("automation", "workflow", "integration", "ops"),
    "sales_conversion": ("sales", "lead", "conversion", "outreach"),
    "brand_content_scale": ("content", "marketing", "brand", "social"),
}


def _contains_any(text: str | None, keywords: tuple[str, ...]) -> bool:
    t = (text or "").strip().lower()
    return any(k in t for k in keywords)


async def get_clone_training_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> CloneTrainingLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))
    employees_result = await db.execute(
        select(Employee).where(
            Employee.organization_id == organization_id,
            Employee.is_active.is_(True),
        ).limit(500)
    )
    employees = list(employees_result.scalars().all())

    id_map_result = await db.execute(
        select(EmployeeIdentityMap).where(EmployeeIdentityMap.organization_id == organization_id).limit(500)
    )
    id_maps = list(id_map_result.scalars().all())
    id_by_emp = {row.employee_id: row for row in id_maps}

    profile_result = await db.execute(
        select(EmployeeCloneProfile).where(EmployeeCloneProfile.organization_id == organization_id).limit(500)
    )
    profiles = list(profile_result.scalars().all())
    profile_by_emp = {row.employee_id: row for row in profiles}

    perf_result = await db.execute(
        select(ClonePerformanceWeekly)
        .where(ClonePerformanceWeekly.organization_id == organization_id)
        .order_by(ClonePerformanceWeekly.week_start_date.desc())
        .limit(500)
    )
    perf_rows = list(perf_result.scalars().all())
    latest_perf_by_emp: dict[int, ClonePerformanceWeekly] = {}
    for row in perf_rows:
        if row.employee_id not in latest_perf_by_emp:
            latest_perf_by_emp[row.employee_id] = row

    plan_result = await db.execute(
        select(RoleTrainingPlan).where(RoleTrainingPlan.organization_id == organization_id).limit(500)
    )
    plans = list(plan_result.scalars().all())
    latest_plan_by_emp: dict[int, RoleTrainingPlan] = {}
    plan_row: RoleTrainingPlan
    for plan_row in sorted(plans, key=lambda x: x.week_start_date, reverse=True):
        if plan_row.employee_id not in latest_plan_by_emp:
            latest_plan_by_emp[plan_row.employee_id] = plan_row
    open_training_plans = len(
        [
            row
            for row in latest_plan_by_emp.values()
            if row.status == "OPEN" and row.week_start_date >= since
        ]
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

    contacts_result = await db.execute(select(Contact).where(Contact.organization_id == organization_id).limit(1000))
    contacts = list(contacts_result.scalars().all())
    business_contacts = [c for c in contacts if (c.relationship or "").lower() == "business"]
    new_business_contacts = [
        c for c in business_contacts
        if c.created_at is not None and c.created_at.date() >= since
    ]

    tasks_result = await db.execute(
        select(Task).where(Task.organization_id == organization_id, Task.is_done.is_(False)).limit(1000)
    )
    tasks = list(tasks_result.scalars().all())
    follow_up_tasks = [
        t for t in tasks
        if _contains_any(t.title, _MARKETING_TASK_KEYWORDS)
        or _contains_any(t.description, _MARKETING_TASK_KEYWORDS)
        or (t.category or "").lower() == "business"
    ]

    employees_result = await db.execute(
        select(Employee).where(Employee.organization_id == organization_id, Employee.is_active.is_(True)).limit(500)
    )
    employees = list(employees_result.scalars().all())

    perf_result = await db.execute(
        select(ClonePerformanceWeekly)
        .where(ClonePerformanceWeekly.organization_id == organization_id)
        .order_by(ClonePerformanceWeekly.week_start_date.desc())
        .limit(500)
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
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))
    contacts_result = await db.execute(
        select(Contact).where(Contact.organization_id == organization_id)
    )
    contacts = list(contacts_result.scalars().all())
    business_contacts = [
        c for c in contacts
        if (c.relationship or "").lower() == "business"
        and c.created_at is not None
        and c.created_at.date() >= since
    ]

    employees_result = await db.execute(
        select(Employee).where(
            Employee.organization_id == organization_id,
            Employee.is_active.is_(True),
        ).limit(500)
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
