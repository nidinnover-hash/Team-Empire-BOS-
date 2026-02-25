"""
Weekly metrics computation from IntegrationSignal data.

Derives TaskMetricWeekly, CodeMetricWeekly, CommsMetricWeekly per employee.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.integration_signal import IntegrationSignal
from app.models.ops_metrics import CodeMetricWeekly, CommsMetricWeekly, TaskMetricWeekly

logger = logging.getLogger(__name__)


def _monday_of(d: date) -> date:
    """Return the Monday of the week containing `d`."""
    return d - timedelta(days=d.weekday())


async def compute_weekly_metrics(
    db: AsyncSession,
    org_id: int,
    weeks: int = 1,
) -> dict[str, int]:
    """
    Compute metrics for the last N weeks from IntegrationSignal data.
    Returns summary of what was computed.
    """
    today = date.today()
    current_monday = _monday_of(today)
    results = {"weeks_computed": 0, "employees_processed": 0, "task_metrics": 0, "code_metrics": 0, "comms_metrics": 0}

    # Get all active employees
    emp_result = await db.execute(
        select(Employee).where(Employee.organization_id == org_id, Employee.is_active == True)  # noqa: E712
    )
    employees = list(emp_result.scalars().all())
    if not employees:
        return results

    for week_offset in range(weeks):
        week_start = current_monday - timedelta(weeks=week_offset)
        week_end_dt = datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc) + timedelta(days=7)
        week_start_dt = datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc)

        # Fetch all signals for this week
        sig_result = await db.execute(
            select(IntegrationSignal).where(
                IntegrationSignal.organization_id == org_id,
                IntegrationSignal.timestamp >= week_start_dt,
                IntegrationSignal.timestamp < week_end_dt,
            )
        )
        signals = list(sig_result.scalars().all())

        # Group signals by employee and source
        emp_signals: dict[int, dict[str, list[IntegrationSignal]]] = {}
        for sig in signals:
            if sig.employee_id is None:
                continue
            if sig.employee_id not in emp_signals:
                emp_signals[sig.employee_id] = {"clickup": [], "github": [], "gmail": []}
            source = sig.source
            if source in emp_signals[sig.employee_id]:
                emp_signals[sig.employee_id][source].append(sig)

        for emp in employees:
            sigs = emp_signals.get(emp.id, {"clickup": [], "github": [], "gmail": []})

            # ---- Task Metrics (from ClickUp signals) ----
            clickup_sigs = sigs["clickup"]
            tasks_assigned = len(clickup_sigs)
            tasks_completed = 0
            on_time_count = 0
            reopen_count = 0

            for sig in clickup_sigs:
                try:
                    payload = json.loads(sig.payload_json) if isinstance(sig.payload_json, str) else sig.payload_json
                except (json.JSONDecodeError, TypeError):
                    payload = {}

                status = (payload.get("status") or "").lower()
                if status in ("complete", "closed", "done", "resolved"):
                    tasks_completed += 1
                    due = payload.get("due_date")
                    if due:
                        try:
                            due_date = date.fromisoformat(due)
                            if sig.timestamp.date() <= due_date:
                                on_time_count += 1
                        except (ValueError, TypeError) as exc:
                            logger.debug(
                                "Task due_date parse failed for signal=%s: %s",
                                sig.external_id,
                                type(exc).__name__,
                            )
                elif status in ("reopened", "reopen"):
                    reopen_count += 1

            on_time_rate = (on_time_count / tasks_completed) if tasks_completed > 0 else 0.0

            await _upsert_task_metric(
                db, org_id, emp.id, week_start,
                tasks_assigned, tasks_completed, on_time_rate, 0.0, reopen_count,
            )
            results["task_metrics"] += 1

            # ---- Code Metrics (from GitHub signals) ----
            github_sigs = sigs["github"]
            prs_opened = 0
            prs_merged = 0
            reviews_done = 0
            issue_links = 0
            files_touched = 0

            for sig in github_sigs:
                try:
                    payload = json.loads(sig.payload_json) if isinstance(sig.payload_json, str) else sig.payload_json
                except (json.JSONDecodeError, TypeError):
                    payload = {}

                ext_id = sig.external_id
                if ext_id.startswith("pr:"):
                    prs_opened += 1
                    if payload.get("merged"):
                        prs_merged += 1
                    files_touched += payload.get("changed_files", 0)
                    reviews_done += payload.get("review_comments", 0)
                elif ext_id.startswith("issue:"):
                    issue_links += 1

            await _upsert_code_metric(
                db, org_id, emp.id, week_start,
                commits=0,  # Commits require separate API call not yet ingested
                prs_opened=prs_opened,
                prs_merged=prs_merged,
                reviews_done=reviews_done,
                issue_links=issue_links,
                files_touched_count=files_touched,
            )
            results["code_metrics"] += 1

            # ---- Comms Metrics (from Gmail signals) ----
            gmail_sigs = sigs["gmail"]
            emails_sent = 0
            emails_replied = 0

            for sig in gmail_sigs:
                try:
                    payload = json.loads(sig.payload_json) if isinstance(sig.payload_json, str) else sig.payload_json
                except (json.JSONDecodeError, TypeError):
                    payload = {}
                emails_sent += 1
                subject = (payload.get("subject") or "").lower()
                if subject.startswith("re:"):
                    emails_replied += 1

            await _upsert_comms_metric(
                db, org_id, emp.id, week_start,
                emails_sent=emails_sent,
                emails_replied=emails_replied,
                median_reply_time_minutes=0.0,  # Would need thread analysis
                escalation_count=0,
            )
            results["comms_metrics"] += 1
            results["employees_processed"] += 1

        results["weeks_computed"] += 1

    await db.commit()
    return results


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

async def _upsert_task_metric(
    db: AsyncSession, org_id: int, employee_id: int, week_start: date,
    tasks_assigned: int, tasks_completed: int, on_time_rate: float,
    avg_cycle_time_hours: float, reopen_count: int,
) -> None:
    result = await db.execute(
        select(TaskMetricWeekly).where(
            TaskMetricWeekly.organization_id == org_id,
            TaskMetricWeekly.employee_id == employee_id,
            TaskMetricWeekly.week_start_date == week_start,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.tasks_assigned = tasks_assigned
        existing.tasks_completed = tasks_completed
        existing.on_time_rate = on_time_rate
        existing.avg_cycle_time_hours = avg_cycle_time_hours
        existing.reopen_count = reopen_count
    else:
        db.add(TaskMetricWeekly(
            organization_id=org_id, employee_id=employee_id, week_start_date=week_start,
            tasks_assigned=tasks_assigned, tasks_completed=tasks_completed,
            on_time_rate=on_time_rate, avg_cycle_time_hours=avg_cycle_time_hours,
            reopen_count=reopen_count,
        ))


async def _upsert_code_metric(
    db: AsyncSession, org_id: int, employee_id: int, week_start: date,
    commits: int, prs_opened: int, prs_merged: int, reviews_done: int,
    issue_links: int, files_touched_count: int,
) -> None:
    result = await db.execute(
        select(CodeMetricWeekly).where(
            CodeMetricWeekly.organization_id == org_id,
            CodeMetricWeekly.employee_id == employee_id,
            CodeMetricWeekly.week_start_date == week_start,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.commits = commits
        existing.prs_opened = prs_opened
        existing.prs_merged = prs_merged
        existing.reviews_done = reviews_done
        existing.issue_links = issue_links
        existing.files_touched_count = files_touched_count
    else:
        db.add(CodeMetricWeekly(
            organization_id=org_id, employee_id=employee_id, week_start_date=week_start,
            commits=commits, prs_opened=prs_opened, prs_merged=prs_merged,
            reviews_done=reviews_done, issue_links=issue_links,
            files_touched_count=files_touched_count,
        ))


async def _upsert_comms_metric(
    db: AsyncSession, org_id: int, employee_id: int, week_start: date,
    emails_sent: int, emails_replied: int, median_reply_time_minutes: float,
    escalation_count: int,
) -> None:
    result = await db.execute(
        select(CommsMetricWeekly).where(
            CommsMetricWeekly.organization_id == org_id,
            CommsMetricWeekly.employee_id == employee_id,
            CommsMetricWeekly.week_start_date == week_start,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.emails_sent = emails_sent
        existing.emails_replied = emails_replied
        existing.median_reply_time_minutes = median_reply_time_minutes
        existing.escalation_count = escalation_count
    else:
        db.add(CommsMetricWeekly(
            organization_id=org_id, employee_id=employee_id, week_start_date=week_start,
            emails_sent=emails_sent, emails_replied=emails_replied,
            median_reply_time_minutes=median_reply_time_minutes,
            escalation_count=escalation_count,
        ))
