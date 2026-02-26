"""
Pattern analysis service — closes the feedback loop between
ops intelligence (signals/metrics) and AI decision-making (memory context).

Reads from:
- TaskMetricWeekly, CodeMetricWeekly, CommsMetricWeekly (work velocity)
- DecisionLog (CEO decision patterns)
- Event (approval/rejection patterns, action outcomes)
- Employee (team member mapping)

Produces: structured text blocks for injection into build_memory_context().
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.decision_log import DecisionLog
from app.models.employee import Employee
from app.models.event import Event
from app.models.ops_metrics import CodeMetricWeekly, CommsMetricWeekly, TaskMetricWeekly
from app.models.policy_rule import PolicyRule


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def build_work_patterns_context(
    db: AsyncSession,
    org_id: int,
    weeks: int = 2,
) -> str:
    """
    Build a structured text block summarizing recent work patterns.
    Injected into AI memory context so the clone reasons about real data.
    """
    blocks: list[str] = []

    # --- Team velocity snapshot ---
    velocity = await _team_velocity_snapshot(db, org_id, weeks)
    if velocity:
        blocks.append(velocity)

    # --- Decision patterns ---
    decision_block = await _decision_pattern_summary(db, org_id)
    if decision_block:
        blocks.append(decision_block)

    # --- Approval/rejection behavior ---
    approval_block = await _approval_behavior_summary(db, org_id)
    if approval_block:
        blocks.append(approval_block)

    # --- Active policies ---
    policy_block = await _active_policies_summary(db, org_id)
    if policy_block:
        blocks.append(policy_block)

    if not blocks:
        return ""

    return "[WORK PATTERNS & INSIGHTS]\n" + "\n\n".join(blocks) + "\n[END WORK PATTERNS]"


async def _team_velocity_snapshot(
    db: AsyncSession,
    org_id: int,
    weeks: int,
) -> str:
    """Summarize team task/code/comms metrics for the last N weeks."""
    cutoff = _monday_of(date.today()) - timedelta(weeks=weeks - 1)

    # Task metrics
    task_result = await db.execute(
        select(
            Employee.name,
            func.sum(TaskMetricWeekly.tasks_assigned).label("assigned"),
            func.sum(TaskMetricWeekly.tasks_completed).label("completed"),
            func.avg(TaskMetricWeekly.on_time_rate).label("on_time"),
            func.sum(TaskMetricWeekly.reopen_count).label("reopens"),
        )
        .join(Employee, Employee.id == TaskMetricWeekly.employee_id)
        .where(
            TaskMetricWeekly.organization_id == org_id,
            TaskMetricWeekly.week_start_date >= cutoff,
        )
        .group_by(Employee.name)
    )
    task_rows = task_result.all()

    # Code metrics
    code_result = await db.execute(
        select(
            Employee.name,
            func.sum(CodeMetricWeekly.prs_opened).label("prs_opened"),
            func.sum(CodeMetricWeekly.prs_merged).label("prs_merged"),
            func.sum(CodeMetricWeekly.reviews_done).label("reviews"),
            func.sum(CodeMetricWeekly.files_touched_count).label("files"),
        )
        .join(Employee, Employee.id == CodeMetricWeekly.employee_id)
        .where(
            CodeMetricWeekly.organization_id == org_id,
            CodeMetricWeekly.week_start_date >= cutoff,
        )
        .group_by(Employee.name)
    )
    code_rows = code_result.all()

    # Comms metrics
    comms_result = await db.execute(
        select(
            Employee.name,
            func.sum(CommsMetricWeekly.emails_sent).label("sent"),
            func.sum(CommsMetricWeekly.emails_replied).label("replied"),
            func.avg(CommsMetricWeekly.median_reply_time_minutes).label("reply_min"),
        )
        .join(Employee, Employee.id == CommsMetricWeekly.employee_id)
        .where(
            CommsMetricWeekly.organization_id == org_id,
            CommsMetricWeekly.week_start_date >= cutoff,
        )
        .group_by(Employee.name)
    )
    comms_rows = comms_result.all()

    if not task_rows and not code_rows and not comms_rows:
        return ""

    lines = [f"Team velocity (last {weeks} weeks):"]

    if task_rows:
        lines.append("  Tasks:")
        for row in task_rows:
            assigned = int(row.assigned or 0)
            completed = int(row.completed or 0)
            on_time = float(row.on_time or 0)
            reopens = int(row.reopens or 0)
            pct = f"{completed}/{assigned}" if assigned else "0/0"
            flags = []
            if on_time < 0.6 and assigned > 0:
                flags.append("LOW on-time rate")
            if reopens > 2:
                flags.append(f"{reopens} reopens")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"    {row.name}: {pct} completed, {on_time:.0%} on-time{flag_str}")

    if code_rows:
        lines.append("  Code:")
        for row in code_rows:
            merged = int(row.prs_merged or 0)
            opened = int(row.prs_opened or 0)
            reviews = int(row.reviews or 0)
            lines.append(f"    {row.name}: {opened} PRs opened, {merged} merged, {reviews} reviews")

    if comms_rows:
        lines.append("  Comms:")
        for row in comms_rows:
            sent = int(row.sent or 0)
            replied = int(row.replied or 0)
            reply_min = float(row.reply_min or 0)
            lines.append(f"    {row.name}: {sent} sent, {replied} replied, avg {reply_min:.0f}min reply time")

    return "\n".join(lines)


async def _decision_pattern_summary(
    db: AsyncSession,
    org_id: int,
    limit: int = 30,
) -> str:
    """Summarize recent decision patterns — what does the CEO tend to approve/reject?"""
    result = await db.execute(
        select(DecisionLog)
        .where(DecisionLog.organization_id == org_id)
        .order_by(DecisionLog.created_at.desc())
        .limit(limit)
    )
    decisions = list(result.scalars().all())
    if not decisions:
        return ""

    counts: dict[str, int] = {}
    for d in decisions:
        counts[d.decision_type] = counts.get(d.decision_type, 0) + 1

    total = len(decisions)
    lines = [f"Decision patterns (last {total} decisions):"]
    for dtype, count in sorted(counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        lines.append(f"  {dtype}: {count} ({pct:.0f}%)")

    # Extract common themes from contexts
    recent_approvals = [d for d in decisions[:10] if d.decision_type == "approve"]
    recent_rejections = [d for d in decisions[:10] if d.decision_type == "reject"]

    if recent_approvals:
        lines.append("  Recent approvals:")
        for d in recent_approvals[:3]:
            ctx = (d.context or "")[:80]
            lines.append(f"    - {ctx}")

    if recent_rejections:
        lines.append("  Recent rejections:")
        for d in recent_rejections[:3]:
            ctx = (d.context or "")[:80]
            reason = (d.reason or "")[:60]
            lines.append(f"    - {ctx} (reason: {reason})")

    return "\n".join(lines)


async def _approval_behavior_summary(
    db: AsyncSession,
    org_id: int,
) -> str:
    """Analyze recent approval/execution events to detect behavioral patterns."""
    cutoff = datetime.now(UTC) - timedelta(days=14)

    result = await db.execute(
        select(Event.event_type, func.count(Event.id))
        .where(
            Event.organization_id == org_id,
            Event.created_at >= cutoff,
            Event.event_type.in_([
                "approval_approved",
                "approval_rejected",
                "approval_executed",
                "execution_failed",
                "email_draft_created",
                "email_sent",
                "task_created",
                "task_updated",
                "daily_run_drafted",
                "chat_memory_learned",
                "agent_chat",
            ]),
        )
        .group_by(Event.event_type)
    )
    rows = result.all()
    if not rows:
        return ""

    event_counts = {str(row[0]): int(row[1]) for row in rows}
    total_approvals = event_counts.get("approval_approved", 0)
    total_rejections = event_counts.get("approval_rejected", 0)
    total_executions = event_counts.get("approval_executed", 0)
    total_failures = event_counts.get("execution_failed", 0)

    lines = ["Action patterns (last 14 days):"]

    if total_approvals or total_rejections:
        total = total_approvals + total_rejections
        approve_rate = total_approvals / total * 100 if total else 0
        lines.append(f"  Approvals: {total_approvals}/{total} ({approve_rate:.0f}% approval rate)")

    if total_executions or total_failures:
        total = total_executions + total_failures
        success_rate = total_executions / total * 100 if total else 0
        lines.append(f"  Executions: {total_executions}/{total} ({success_rate:.0f}% success rate)")

    chat_count = event_counts.get("agent_chat", 0)
    learned_count = event_counts.get("chat_memory_learned", 0)
    if chat_count:
        lines.append(f"  Chat interactions: {chat_count} conversations, {learned_count} memory items learned")

    tasks_created = event_counts.get("task_created", 0)
    tasks_updated = event_counts.get("task_updated", 0)
    if tasks_created or tasks_updated:
        lines.append(f"  Task activity: {tasks_created} created, {tasks_updated} updated")

    drafts = event_counts.get("email_draft_created", 0)
    sent = event_counts.get("email_sent", 0)
    if drafts:
        lines.append(f"  Email: {drafts} drafts, {sent} sent")

    return "\n".join(lines)


async def _active_policies_summary(
    db: AsyncSession,
    org_id: int,
) -> str:
    """List active policy rules so the AI knows what guardrails are in effect."""
    result = await db.execute(
        select(PolicyRule)
        .where(
            PolicyRule.organization_id == org_id,
            PolicyRule.is_active.is_(True),
        )
        .order_by(PolicyRule.created_at.desc())
        .limit(10)
    )
    policies = list(result.scalars().all())
    if not policies:
        return ""

    lines = [f"Active policies ({len(policies)}):"]
    for p in policies:
        rule = (p.rule_text or "")[:100]
        lines.append(f"  - {p.title}: {rule}")

    return "\n".join(lines)
