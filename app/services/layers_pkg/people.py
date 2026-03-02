"""People layers — training, employee performance, management, revenue, staff, AI routing, prosperity."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
from app.services.layers_pkg.helpers import (
    PenaltyRule,
    RiskRule,
    apply_penalties,
    apply_risk_rules,
    avg_ai_level,
    contains_any,
    safe_query,
)

_TRAINING_KEYWORDS = ("train", "training", "learn", "learning", "course", "cert", "practice", "upskill", "ai")
_RISK_NOTE_KEYWORDS = ("blocked", "struggling", "late", "delay", "help needed")
logger = logging.getLogger(__name__)

_AI_NICHE_MAP: dict[str, tuple[str, ...]] = {
    "automation_ops": ("automation", "ops", "workflow", "zapier", "integration"),
    "sales_growth_ai": ("sales", "lead", "outreach", "crm", "conversion"),
    "customer_support_ai": ("support", "service", "ticket", "customer"),
    "content_brand_ai": ("content", "marketing", "social", "brand", "copy"),
    "analytics_strategy_ai": ("analytics", "data", "dashboard", "kpi", "metric"),
}

# ── Penalty rule sets ────────────────────────────────────────────────────────

_TRAINING_LAYER_PENALTIES: list[PenaltyRule] = [
    (
        lambda ctx: ctx["active"] > 0 and ctx["avg_ai"] < settings.LAYER_MIN_AI_LEVEL,
        25,
        "Average AI skill maturity across the team is below target.",
        "Run weekly hands-on AI workflow training by role.",
    ),
    (
        lambda ctx: ctx["open_training"] < settings.LAYER_MIN_TRAINING_TASKS,
        15,
        "Training task pipeline is too small for continuous capability growth.",
        "Create a recurring training backlog for every team.",
    ),
    (
        lambda ctx: ctx["due_soon"] > settings.LAYER_MAX_DUE_SOON_TASKS,
        15,
        "Too many training tasks are due soon; completion risk is high.",
        "Resequence training tasks into realistic weekly batches.",
    ),
    (
        lambda ctx: ctx["recent_notes"] < 3,
        10,
        "Low recent training notes reduce visibility of team learning progress.",
        "Log key learning outcomes daily in Data Hub.",
    ),
]

_EMPLOYEE_PERF_PENALTIES: list[PenaltyRule] = [
    (
        lambda ctx: ctx["active"] == 0,
        40,
        "No active team members configured in memory.",
        "Add your org structure in Memory > Team to unlock performance analytics.",
    ),
    (
        lambda ctx: ctx["active"] > 0 and ctx["low_ai_ratio"] > 0.4,
        20,
        "Large share of team has low AI maturity.",
        "Run role-based AI training for members at level 1-2.",
    ),
    (
        lambda ctx: ctx["overdue"] > max(3, ctx["active"]),
        20,
        "Operational task backlog is aging past due dates.",
        "Execute a 48-hour overdue-task recovery sprint with daily check-ins.",
    ),
    (
        lambda ctx: ctx["blockers"] > max(2, ctx["active"] // 2),
        15,
        "Blocker event volume is high in the selected window.",
        "Assign explicit blocker owners and enforce same-day resolution updates.",
    ),
]

_EMPLOYEE_MGMT_PENALTIES: list[PenaltyRule] = [
    (
        lambda ctx: ctx["active"] == 0,
        40,
        "No active employees found in employee directory.",
        "Add employee records and mark active team members.",
    ),
    (
        lambda ctx: ctx["total"] > 0 and ctx["unmapped_ratio"] > settings.LAYER_UNMAPPED_THRESHOLD,
        20,
        "Large share of employees are not mapped to GitHub/ClickUp identities.",
        "Map each employee to GitHub username and ClickUp user ID.",
    ),
    (
        lambda ctx: ctx["active"] > 0 and ctx["overdue"] > ctx["active"],
        20,
        "Overdue task load exceeds active employee capacity.",
        "Run manager triage to reassign or close stale work items.",
    ),
    (
        lambda ctx: ctx["total"] > 0 and ctx["github_mapped"] < max(1, int(ctx["total"] * settings.LAYER_IDENTITY_COVERAGE)),
        10,
        "GitHub mapping coverage is low.",
        "Enforce GitHub identity mapping for all technical roles.",
    ),
]

_REVENUE_PENALTIES: list[PenaltyRule] = [
    (
        lambda ctx: ctx["income"] <= 0,
        35,
        "No income recorded in selected window.",
        "Verify invoicing and revenue capture pipeline.",
    ),
    (
        lambda ctx: ctx["net"] < 0,
        30,
        "Net revenue is negative for selected window.",
        "Cut low-ROI spend and prioritize high-conversion channels.",
    ),
    (
        lambda ctx: ctx["recurring_ratio"] > settings.LAYER_RECURRING_EXPENSE_CAP,
        15,
        "Recurring expense ratio is high.",
        "Run SaaS/license audit and remove underused tools.",
    ),
    (
        lambda ctx: ctx["income"] > 0 and ctx["expense"] > ctx["income"] * 0.8,
        10,
        "Expense-to-income ratio is approaching unhealthy range.",
        "Set weekly budget guardrails per cost center.",
    ),
]

_STAFF_TRAINING_PENALTIES: list[PenaltyRule] = [
    (
        lambda ctx: ctx["active"] == 0,
        40,
        "No active staff entries in team memory.",
        "Add active staff to memory/team for training governance.",
    ),
    (
        lambda ctx: ctx["active"] > 0 and ctx["avg_ai"] < settings.LAYER_MIN_AI_LEVEL,
        25,
        "Average AI maturity of staff is below target.",
        "Run role-based weekly AI training sprint.",
    ),
    (
        lambda ctx: ctx["open_training"] < max(3, ctx["active"]),
        15,
        "Training backlog is too small to sustain upskilling.",
        "Create training backlog per staff role.",
    ),
    (
        lambda ctx: ctx["due_soon"] > max(4, ctx["active"]),
        10,
        "Too many training tasks due soon can reduce completion quality.",
        "Re-sequence due dates and assign staff owners clearly.",
    ),
]

_PROSPERITY_RISKS: list[RiskRule] = [
    (
        lambda ctx: ctx["overdue"] > max(2, ctx["active"]),
        "Overdue workload may reduce team happiness and autonomy.",
        "Run a 48-hour workload reset and remove low-value tasks.",
    ),
    (
        lambda ctx: ctx["net"] <= 0,
        "Net financial performance is not supporting growth incentives.",
        "Improve conversion and reduce non-essential spend immediately.",
    ),
    (
        lambda ctx: ctx["avg_ai"] < settings.LAYER_MIN_AI_LEVEL and ctx["active"] > 0,
        "AI maturity gap is limiting opportunity and freedom.",
        "Launch role-based AI coaching for all teams this week.",
    ),
]


# ── Domain helpers ───────────────────────────────────────────────────────────


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
    if contains_any(member.notes, _RISK_NOTE_KEYWORDS):
        risk_flags.append("Risk signal in notes")
        score -= 15

    return max(0, min(100, score)), risk_flags


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
    best_niche = "unclassified"
    best_hits: list[str] = []
    for niche, keywords in _AI_NICHE_MAP.items():
        hits = [k for k in keywords if k in text]
        if len(hits) > len(best_hits):
            best_niche = niche
            best_hits = hits
    confidence = min(1.0, 0.45 + (0.1 * len(best_hits)))
    return best_niche, best_hits[:4], confidence


# ── Active-members query (reused in multiple layers) ─────────────────────────

async def _get_active_members(
    db: AsyncSession, organization_id: int, label: str,
) -> list:
    return await safe_query(
        db,
        select(TeamMember).where(
            TeamMember.organization_id == organization_id,
            TeamMember.is_active.is_(True),
        ).limit(settings.LAYER_QUERY_LIMIT),
        label, organization_id,
    )


async def _get_open_tasks(
    db: AsyncSession, organization_id: int, label: str,
) -> list:
    return await safe_query(
        db,
        select(Task).where(
            Task.organization_id == organization_id,
            Task.is_done.is_(False),
        ).limit(settings.LAYER_QUERY_LIMIT),
        label, organization_id,
    )


# ── Layer functions ──────────────────────────────────────────────────────────


async def get_training_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> TrainingLayerReport:
    today = date.today()

    members = await _get_active_members(db, organization_id, "training:members")
    active_team_members = len(members)
    ai_avg = avg_ai_level(members)

    tasks = await _get_open_tasks(db, organization_id, "training:tasks")
    open_training_tasks = [
        t for t in tasks
        if contains_any(t.title, _TRAINING_KEYWORDS)
        or contains_any(t.description, _TRAINING_KEYWORDS)
    ]
    due_soon_training_tasks = [
        t for t in open_training_tasks
        if t.due_date is not None and t.due_date <= (today + timedelta(days=14))
    ]

    notes = await safe_query(
        db,
        select(Note).where(Note.organization_id == organization_id)
        .order_by(Note.created_at.desc()).limit(40),
        "training:notes", organization_id,
    )
    recent_training_notes = [n for n in notes if contains_any(n.content, _TRAINING_KEYWORDS)]

    penalty_ctx = {
        "active": active_team_members,
        "avg_ai": ai_avg,
        "open_training": len(open_training_tasks),
        "due_soon": len(due_soon_training_tasks),
        "recent_notes": len(recent_training_notes),
    }
    score, blockers, next_actions = apply_penalties(
        _TRAINING_LAYER_PENALTIES, penalty_ctx,
        "Maintain current training cadence and track completion weekly.",
    )

    return TrainingLayerReport(
        window_days=window_days,
        active_team_members=active_team_members,
        avg_ai_level=ai_avg,
        open_training_tasks=len(open_training_tasks),
        due_soon_training_tasks=len(due_soon_training_tasks),
        recent_training_notes=len(recent_training_notes),
        training_score=score,
        blockers=blockers,
        next_actions=next_actions,
    )


async def get_employee_performance_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> EmployeePerformanceLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))

    members = await _get_active_members(db, organization_id, "employee_perf:members")
    active_team_members = len(members)
    ai_avg = avg_ai_level(members)
    low_ai_members = len([m for m in members if (m.ai_level or 1) <= 2])
    high_ai_members = len([m for m in members if (m.ai_level or 1) >= 4])

    tasks = await _get_open_tasks(db, organization_id, "employee_perf:tasks")
    open_operational_tasks = [
        t for t in tasks
        if not contains_any(t.title, _TRAINING_KEYWORDS)
        and not contains_any(t.description, _TRAINING_KEYWORDS)
    ]
    overdue_operational_tasks = [
        t for t in open_operational_tasks
        if t.due_date is not None and t.due_date < today
    ]

    blockers_rows = await safe_query(
        db,
        select(DailyContext).where(
            DailyContext.organization_id == organization_id,
            DailyContext.context_type == "blocker",
            DailyContext.date >= since,
            DailyContext.date <= today,
        ),
        "employee_perf:blockers", organization_id,
    )

    snapshots: list[EmployeePerformanceMember] = []
    for member in sorted(members, key=lambda m: ((m.team or ""), (m.name or "").lower())):
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

    penalty_ctx = {
        "active": active_team_members,
        "low_ai_ratio": low_ai_members / active_team_members if active_team_members else 0,
        "overdue": len(overdue_operational_tasks),
        "blockers": len(blockers_rows),
    }
    score, top_risks, next_actions = apply_penalties(
        _EMPLOYEE_PERF_PENALTIES, penalty_ctx,
        "Maintain current execution cadence and review employee score weekly.",
    )

    return EmployeePerformanceLayerReport(
        window_days=window_days,
        active_team_members=active_team_members,
        avg_ai_level=ai_avg,
        low_ai_members=low_ai_members,
        high_ai_members=high_ai_members,
        open_operational_tasks=len(open_operational_tasks),
        overdue_operational_tasks=len(overdue_operational_tasks),
        blocker_events_in_window=len(blockers_rows),
        performance_score=score,
        top_risks=top_risks,
        next_actions=next_actions,
        members=snapshots[:20],
    )


async def get_employee_management_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> EmployeeManagementLayerReport:
    ql = settings.LAYER_QUERY_LIMIT

    employees = await safe_query(
        db,
        select(Employee).where(Employee.organization_id == organization_id).limit(ql),
        "emp_mgmt:employees", organization_id,
    )
    total_employees = len(employees)
    active_employees = len([e for e in employees if bool(e.is_active)])
    inactive_employees = max(0, total_employees - active_employees)
    github_mapped = len([e for e in employees if (e.github_username or "").strip()])
    clickup_mapped = len([e for e in employees if (e.clickup_user_id or "").strip()])
    unmapped = len(
        [e for e in employees if not (e.github_username or "").strip() and not (e.clickup_user_id or "").strip()]
    )

    tasks = await _get_open_tasks(db, organization_id, "emp_mgmt:tasks")
    today = date.today()
    open_tasks = len(tasks)
    overdue_tasks = len([t for t in tasks if t.due_date is not None and t.due_date < today])

    # ClickUp penalty is separate since it uses the same threshold but different message
    penalty_ctx = {
        "total": total_employees,
        "active": active_employees,
        "unmapped_ratio": unmapped / max(total_employees, 1),
        "overdue": overdue_tasks,
        "github_mapped": github_mapped,
    }
    score, top_risks, next_actions = apply_penalties(
        _EMPLOYEE_MGMT_PENALTIES, penalty_ctx,
        "Keep current employee management cadence and review weekly.",
    )
    # Additional ClickUp penalty (5th rule, beyond the 4-rule limit of the declarative list)
    if total_employees > 0 and clickup_mapped < max(1, int(total_employees * settings.LAYER_IDENTITY_COVERAGE)):
        score = max(0, score - 10)
        top_risks.append("ClickUp mapping coverage is low.")
        next_actions.append("Enforce ClickUp user mapping for operational visibility.")
        top_risks = top_risks[:4]
        next_actions = next_actions[:4]

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
        top_risks=top_risks,
        next_actions=next_actions,
    )


async def get_revenue_management_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> RevenueManagementLayerReport:
    today = date.today()
    since = today - timedelta(days=max(window_days - 1, 0))

    entries = await safe_query(
        db,
        select(FinanceEntry).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.entry_date >= since,
            FinanceEntry.entry_date <= today,
        ),
        "revenue:finance", organization_id,
    )

    income = float(sum((e.amount or 0) for e in entries if e.type == "income"))
    expense = float(sum((e.amount or 0) for e in entries if e.type == "expense"))
    net = income - expense
    recurring_keywords = ("subscription", "saas", "tool", "license", "retainer")
    recurring_expense = float(
        sum(
            (e.amount or 0)
            for e in entries
            if e.type == "expense"
            and (contains_any(e.category, recurring_keywords) or contains_any(e.description, recurring_keywords))
        )
    )
    recurring_ratio = (recurring_expense / expense) if expense > 0 else 0.0

    penalty_ctx = {
        "income": income,
        "expense": expense,
        "net": net,
        "recurring_ratio": recurring_ratio,
    }
    score, top_risks, next_actions = apply_penalties(
        _REVENUE_PENALTIES, penalty_ctx,
        "Maintain current revenue discipline and monitor weekly cash flow.",
    )

    return RevenueManagementLayerReport(
        window_days=window_days,
        income_in_window=income,
        expense_in_window=expense,
        net_in_window=net,
        recurring_expense_ratio=round(recurring_ratio, 4),
        revenue_health_score=score,
        top_risks=top_risks,
        next_actions=next_actions,
    )


async def get_staff_training_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> StaffTrainingLayerReport:
    today = date.today()

    members = await _get_active_members(db, organization_id, "staff_training:members")
    active_staff = len(members)
    ai_avg = avg_ai_level(members)
    low_ai = len([m for m in members if (m.ai_level or 1) <= 2])

    tasks = await _get_open_tasks(db, organization_id, "staff_training:tasks")
    open_training_tasks = [
        t for t in tasks
        if contains_any(t.title, _TRAINING_KEYWORDS)
        or contains_any(t.description, _TRAINING_KEYWORDS)
    ]
    due_soon_training_tasks = [
        t for t in open_training_tasks
        if t.due_date is not None and t.due_date <= (today + timedelta(days=14))
    ]

    penalty_ctx = {
        "active": active_staff,
        "avg_ai": ai_avg,
        "open_training": len(open_training_tasks),
        "due_soon": len(due_soon_training_tasks),
    }
    score, top_risks, next_actions = apply_penalties(
        _STAFF_TRAINING_PENALTIES, penalty_ctx,
        "Maintain training cadence and audit staff progress weekly.",
    )

    return StaffTrainingLayerReport(
        window_days=window_days,
        active_staff=active_staff,
        avg_ai_level=ai_avg,
        low_ai_level_staff=low_ai,
        open_training_tasks=len(open_training_tasks),
        due_soon_training_tasks=len(due_soon_training_tasks),
        training_velocity_score=score,
        top_risks=top_risks,
        next_actions=next_actions,
    )


async def get_ai_skill_routing_layer(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> AISkillRoutingLayerReport:
    members = await _get_active_members(db, organization_id, "ai_routing:members")
    active_staff = len(members)
    ai_avg = avg_ai_level(members)

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
    routing_score = max(0, min(100, int(40 + (ai_avg * 12) + (len(top_opportunities) * 8))))
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
        avg_ai_level=ai_avg,
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

    members = await _get_active_members(db, organization_id, "prosperity:members")
    active_staff = len(members)
    # avg_ai_level returns rounded; we need the raw float for index math
    ai_avg_raw = (sum((m.ai_level or 0) for m in members) / active_staff) if active_staff else 0.0

    tasks = await _get_open_tasks(db, organization_id, "prosperity:tasks")
    overdue = len([t for t in tasks if t.due_date is not None and t.due_date < today])

    entries = await safe_query(
        db,
        select(FinanceEntry).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.entry_date >= since,
            FinanceEntry.entry_date <= today,
        ),
        "prosperity:finance", organization_id,
    )
    income = float(sum((e.amount or 0) for e in entries if e.type == "income"))
    expense = float(sum((e.amount or 0) for e in entries if e.type == "expense"))
    net = income - expense

    opportunity_index = max(0, min(100, int(45 + ai_avg_raw * 10 - overdue * 2)))
    wealth_index = max(0, min(100, (50 + (15 if net > 0 else -15))))
    happiness_index = max(0, min(100, int(70 - overdue * 3)))
    freedom_index = max(0, min(100, int(40 + ai_avg_raw * 8 - overdue * 2)))
    composite = int((opportunity_index + wealth_index + happiness_index + freedom_index) / 4)

    # Prosperity uses its own index-based scoring; risk rules generate risks/actions only
    penalty_ctx = {"overdue": overdue, "net": net, "avg_ai": ai_avg_raw, "active": active_staff}
    top_risks, next_actions = apply_risk_rules(
        _PROSPERITY_RISKS, penalty_ctx,
        "Maintain current growth rhythm and keep weekly reflection discipline.",
    )

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
