"""
Weekly report generation.

Generates markdown reports from computed metrics:
- team_health: delivery score, quality proxy, comms proxy, initiative proxy
- project_risk: at-risk projects based on task completion rates
- founder_review: decisions made, policies active, overall ops health
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.decision_log import DecisionLog
from app.models.employee import Employee
from app.models.ops_metrics import CodeMetricWeekly, CommsMetricWeekly, TaskMetricWeekly
from app.models.policy_rule import PolicyRule
from app.models.weekly_report import WeeklyReport

logger = logging.getLogger(__name__)


async def generate_weekly_report(
    db: AsyncSession,
    org_id: int,
    week_start: date,
    report_type: str,
) -> WeeklyReport:
    """Generate and store a weekly report. Overwrites if already exists for this week+type."""
    if report_type == "team_health":
        content = await _generate_team_health(db, org_id, week_start)
    elif report_type == "project_risk":
        content = await _generate_project_risk(db, org_id, week_start)
    elif report_type == "founder_review":
        content = await _generate_founder_review(db, org_id, week_start)
    else:
        content = f"# Unknown Report Type: {report_type}\n\nNo generator available."

    # Upsert
    result = await db.execute(
        select(WeeklyReport).where(
            WeeklyReport.organization_id == org_id,
            WeeklyReport.week_start_date == week_start,
            WeeklyReport.report_type == report_type,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.content_markdown = content
        report = existing
    else:
        report = WeeklyReport(
            organization_id=org_id,
            week_start_date=week_start,
            report_type=report_type,
            content_markdown=content,
        )
        db.add(report)

    await db.commit()
    await db.refresh(report)
    return report


async def get_report(
    db: AsyncSession, org_id: int, week_start: date, report_type: str,
) -> WeeklyReport | None:
    result = await db.execute(
        select(WeeklyReport).where(
            WeeklyReport.organization_id == org_id,
            WeeklyReport.week_start_date == week_start,
            WeeklyReport.report_type == report_type,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Report generators
# ---------------------------------------------------------------------------

async def _generate_team_health(db: AsyncSession, org_id: int, week_start: date) -> str:
    employees = await _get_employees(db, org_id)
    task_metrics = await _get_task_metrics(db, org_id, week_start)
    code_metrics = await _get_code_metrics(db, org_id, week_start)
    comms_metrics = await _get_comms_metrics(db, org_id, week_start)

    lines = [
        "# Team Health Report",
        f"**Week of {week_start.isoformat()}**",
        "",
        "## Summary Scores",
        "",
        "| Employee | Delivery | Quality Proxy | Comms Proxy | Initiative |",
        "|----------|----------|---------------|-------------|------------|",
    ]

    for emp in employees:
        tm = task_metrics.get(emp.id)
        cm = code_metrics.get(emp.id)
        comms = comms_metrics.get(emp.id)

        # Delivery score: tasks_completed / tasks_assigned (capped at 1.0)
        delivery = 0.0
        if tm and tm.tasks_assigned > 0:
            delivery = min(1.0, tm.tasks_completed / tm.tasks_assigned)

        # Quality proxy: on_time_rate * (1 - reopen_rate)
        quality = 0.0
        if tm:
            reopen_rate = (tm.reopen_count / max(tm.tasks_completed, 1))
            quality = tm.on_time_rate * max(0, 1 - reopen_rate)

        # Comms proxy: emails_replied / emails_sent (engagement)
        comms_score = 0.0
        if comms and comms.emails_sent > 0:
            comms_score = min(1.0, comms.emails_replied / comms.emails_sent)

        # Initiative: PRs opened + issues linked (normalized to 0-1 with 10 as "full")
        initiative = 0.0
        if cm:
            initiative = min(1.0, (cm.prs_opened + cm.issue_links) / 10)

        lines.append(
            f"| {emp.name} | {delivery:.0%} | {quality:.0%} | {comms_score:.0%} | {initiative:.0%} |"
        )

    lines.extend([
        "",
        "## Metric Definitions",
        "- **Delivery**: tasks completed / tasks assigned (from ClickUp)",
        "- **Quality Proxy**: on-time rate * (1 - reopen rate)",
        "- **Comms Proxy**: reply emails / total emails (engagement heuristic)",
        "- **Initiative**: (PRs opened + issues linked) / 10 (GitHub activity)",
        "",
        "## Detailed Breakdown",
        "",
    ])

    for emp in employees:
        tm = task_metrics.get(emp.id)
        cm = code_metrics.get(emp.id)
        comms = comms_metrics.get(emp.id)

        lines.append(f"### {emp.name} ({emp.job_title or 'N/A'})")
        if tm:
            lines.append(f"- Tasks: {tm.tasks_completed}/{tm.tasks_assigned} completed, on-time rate {tm.on_time_rate:.0%}, reopens {tm.reopen_count}")
        else:
            lines.append("- Tasks: No data")
        if cm:
            lines.append(f"- Code: {cm.prs_opened} PRs opened, {cm.prs_merged} merged, {cm.reviews_done} review comments, {cm.files_touched_count} files")
        else:
            lines.append("- Code: No data")
        if comms:
            lines.append(f"- Comms: {comms.emails_sent} sent, {comms.emails_replied} replies, {comms.escalation_count} escalations")
        else:
            lines.append("- Comms: No data")
        lines.append("")

    return "\n".join(lines)


async def _generate_project_risk(db: AsyncSession, org_id: int, week_start: date) -> str:
    employees = await _get_employees(db, org_id)
    task_metrics = await _get_task_metrics(db, org_id, week_start)

    lines = [
        "# Project Risk Report",
        f"**Week of {week_start.isoformat()}**",
        "",
        "## At-Risk Indicators",
        "",
    ]

    at_risk = []
    for emp in employees:
        tm = task_metrics.get(emp.id)
        if not tm:
            continue
        risks = []
        if tm.tasks_assigned > 0 and tm.tasks_completed / tm.tasks_assigned < 0.5:
            risks.append(f"Low completion rate ({tm.tasks_completed}/{tm.tasks_assigned})")
        if tm.on_time_rate < 0.6:
            risks.append(f"On-time rate below 60% ({tm.on_time_rate:.0%})")
        if tm.reopen_count > 2:
            risks.append(f"High reopen count ({tm.reopen_count})")
        if risks:
            at_risk.append((emp, risks))

    if at_risk:
        lines.append("| Employee | Risk Signals |")
        lines.append("|----------|-------------|")
        for emp, risks in at_risk:
            lines.append(f"| {emp.name} | {'; '.join(risks)} |")
    else:
        lines.append("No at-risk signals detected this week.")

    lines.extend([
        "",
        "## Risk Thresholds",
        "- Completion rate < 50%",
        "- On-time rate < 60%",
        "- Reopen count > 2",
        "",
        "*Note: These are heuristic indicators, not direct performance assessments. "
        "Always verify with context before drawing conclusions.*",
    ])

    return "\n".join(lines)


async def _generate_founder_review(db: AsyncSession, org_id: int, week_start: date) -> str:
    week_end = week_start + timedelta(days=7)

    # Count decisions this week
    dec_result = await db.execute(
        select(DecisionLog).where(
            DecisionLog.organization_id == org_id,
            DecisionLog.created_at >= str(week_start),
            DecisionLog.created_at < str(week_end),
        ).limit(2000)
    )
    decisions = list(dec_result.scalars().all())

    # Count active policies
    policy_result = await db.execute(
        select(PolicyRule).where(
            PolicyRule.organization_id == org_id,
            PolicyRule.is_active == True,
        ).limit(500)
    )
    active_policies = list(policy_result.scalars().all())

    employees = await _get_employees(db, org_id)
    task_metrics = await _get_task_metrics(db, org_id, week_start)

    total_assigned = sum(tm.tasks_assigned for tm in task_metrics.values())
    total_completed = sum(tm.tasks_completed for tm in task_metrics.values())

    lines = [
        "# Founder Decision Review",
        f"**Week of {week_start.isoformat()}**",
        "",
        "## Ops Health Snapshot",
        f"- Team size: {len(employees)} active employees",
        f"- Tasks: {total_completed}/{total_assigned} completed across team",
        f"- Decisions logged: {len(decisions)}",
        f"- Active policies: {len(active_policies)}",
        "",
    ]

    if decisions:
        lines.extend(["## Decisions This Week", ""])
        for dec in decisions:
            lines.append(f"- **[{dec.decision_type.upper()}]** {dec.context[:100]}...")
            lines.append(f"  - Reason: {dec.reason[:150]}")
            lines.append("")

    if active_policies:
        lines.extend(["## Active Policies", ""])
        for policy in active_policies:
            lines.append(f"- **{policy.title}**: {policy.rule_text[:100]}...")

    lines.extend([
        "",
        "## Leadership Principles Check",
        "- [ ] Data over intuition: Are decisions backed by metrics?",
        "- [ ] Long-term scalability: Are short-term fixes creating tech debt?",
        "- [ ] Communication structure: Is every instruction a ticket?",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

async def _get_employees(db: AsyncSession, org_id: int) -> list[Employee]:
    result = await db.execute(
        select(Employee).where(Employee.organization_id == org_id, Employee.is_active == True).order_by(Employee.name)
    )
    return list(result.scalars().all())


async def _get_task_metrics(db: AsyncSession, org_id: int, week_start: date) -> dict[int, TaskMetricWeekly]:
    result = await db.execute(
        select(TaskMetricWeekly).where(
            TaskMetricWeekly.organization_id == org_id,
            TaskMetricWeekly.week_start_date == week_start,
        )
    )
    return {m.employee_id: m for m in result.scalars().all()}


async def _get_code_metrics(db: AsyncSession, org_id: int, week_start: date) -> dict[int, CodeMetricWeekly]:
    result = await db.execute(
        select(CodeMetricWeekly).where(
            CodeMetricWeekly.organization_id == org_id,
            CodeMetricWeekly.week_start_date == week_start,
        )
    )
    return {m.employee_id: m for m in result.scalars().all()}


async def _get_comms_metrics(db: AsyncSession, org_id: int, week_start: date) -> dict[int, CommsMetricWeekly]:
    result = await db.execute(
        select(CommsMetricWeekly).where(
            CommsMetricWeekly.organization_id == org_id,
            CommsMetricWeekly.week_start_date == week_start,
        )
    )
    return {m.employee_id: m for m in result.scalars().all()}
