"""
Anomaly detection service — compares today's signal metrics against a
7-day rolling average and emits ANOMALY_DETECTED signals when thresholds
are breached.

Metrics monitored:
  - Tasks completed per day
  - Events (signals) per day
  - Revenue per day (income - expense)
  - Approvals created per day

Detection: if today's value is >2x the rolling average OR <0.3x the rolling
average, it's flagged as an anomaly.
"""

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.event import Event
from app.models.finance import FinanceEntry
from app.models.task import Task
from app.platform.signals import SignalEnvelope, publisher, topics

logger = logging.getLogger(__name__)

# Thresholds: anomaly if ratio outside this range
_HIGH_THRESHOLD = 2.0
_LOW_THRESHOLD = 0.3


async def detect_anomalies(
    db: AsyncSession,
    organization_id: int,
) -> list[dict]:
    """
    Run anomaly detection for today vs 7-day rolling average.
    Returns list of detected anomalies and emits signals for each.
    """
    today = date.today()
    week_ago = today - timedelta(days=7)
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC)

    anomalies: list[dict] = []

    # ── Tasks completed ──────────────────────────────────────────────
    tasks_today = (await db.execute(
        select(func.count(Task.id)).where(
            Task.organization_id == organization_id,
            Task.is_done.is_(True),
            Task.completed_at >= today_start,
        )
    )).scalar_one() or 0

    tasks_7d = (await db.execute(
        select(func.count(Task.id)).where(
            Task.organization_id == organization_id,
            Task.is_done.is_(True),
            Task.completed_at >= datetime.combine(week_ago, datetime.min.time()).replace(tzinfo=UTC),
            Task.completed_at < today_start,
        )
    )).scalar_one() or 0
    tasks_avg = tasks_7d / 7 if tasks_7d else 0

    anomaly = _check_metric("tasks_completed", tasks_today, tasks_avg)
    if anomaly:
        anomalies.append(anomaly)

    # ── Events ───────────────────────────────────────────────────────
    events_today = (await db.execute(
        select(func.count(Event.id)).where(
            Event.organization_id == organization_id,
            Event.created_at >= today_start,
        )
    )).scalar_one() or 0

    events_7d = (await db.execute(
        select(func.count(Event.id)).where(
            Event.organization_id == organization_id,
            Event.created_at >= datetime.combine(week_ago, datetime.min.time()).replace(tzinfo=UTC),
            Event.created_at < today_start,
        )
    )).scalar_one() or 0
    events_avg = events_7d / 7 if events_7d else 0

    anomaly = _check_metric("events", events_today, events_avg)
    if anomaly:
        anomalies.append(anomaly)

    # ── Revenue (income - expense) ───────────────────────────────────
    income_today = (await db.execute(
        select(func.coalesce(func.sum(FinanceEntry.amount), 0)).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.type == "income",
            FinanceEntry.entry_date == today,
        )
    )).scalar_one() or 0

    expense_today = (await db.execute(
        select(func.coalesce(func.sum(FinanceEntry.amount), 0)).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.type == "expense",
            FinanceEntry.entry_date == today,
        )
    )).scalar_one() or 0
    revenue_today = float(income_today) - float(expense_today)

    income_7d = (await db.execute(
        select(func.coalesce(func.sum(FinanceEntry.amount), 0)).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.type == "income",
            FinanceEntry.entry_date >= week_ago,
            FinanceEntry.entry_date < today,
        )
    )).scalar_one() or 0

    expense_7d = (await db.execute(
        select(func.coalesce(func.sum(FinanceEntry.amount), 0)).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.type == "expense",
            FinanceEntry.entry_date >= week_ago,
            FinanceEntry.entry_date < today,
        )
    )).scalar_one() or 0
    revenue_7d = (float(income_7d) - float(expense_7d)) / 7 if income_7d or expense_7d else 0

    anomaly = _check_metric("revenue", revenue_today, revenue_7d)
    if anomaly:
        anomalies.append(anomaly)

    # ── Approvals created ────────────────────────────────────────────
    approvals_today = (await db.execute(
        select(func.count(Approval.id)).where(
            Approval.organization_id == organization_id,
            Approval.created_at >= today_start,
        )
    )).scalar_one() or 0

    approvals_7d = (await db.execute(
        select(func.count(Approval.id)).where(
            Approval.organization_id == organization_id,
            Approval.created_at >= datetime.combine(week_ago, datetime.min.time()).replace(tzinfo=UTC),
            Approval.created_at < today_start,
        )
    )).scalar_one() or 0
    approvals_avg = approvals_7d / 7 if approvals_7d else 0

    anomaly = _check_metric("approvals_created", approvals_today, approvals_avg)
    if anomaly:
        anomalies.append(anomaly)

    # ── Emit signals ─────────────────────────────────────────────────
    for a in anomalies:
        await publisher.publish(SignalEnvelope(
            topic=topics.ANOMALY_DETECTED,
            organization_id=organization_id,
            actor_user_id=None,
            entity_type="anomaly",
            entity_id=a["metric"],
            payload_json=a,
        ))

        # Also create a notification
        from app.services.notification import create_notification
        await create_notification(
            db,
            organization_id=organization_id,
            type="anomaly_detected",
            severity="warning",
            title=f"Anomaly: {a['metric']}",
            message=a["message"],
            source="anomaly_detection",
            entity_type="anomaly",
        )

    if anomalies:
        logger.warning(
            "Detected %d anomalies for org=%d: %s",
            len(anomalies),
            organization_id,
            [a["metric"] for a in anomalies],
        )

    return anomalies


def _check_metric(
    metric: str, today_value: float, avg_value: float,
) -> dict | None:
    """Return an anomaly dict if the metric is outside normal bounds."""
    if avg_value == 0:
        # Can't compute ratio with zero average; only flag if today is unusually high
        if today_value > 10:
            return {
                "metric": metric,
                "today": today_value,
                "rolling_avg_7d": 0,
                "ratio": float("inf"),
                "direction": "spike",
                "message": f"{metric}: {today_value} today vs 0 avg (unexpected spike)",
            }
        return None

    ratio = today_value / avg_value
    if ratio > _HIGH_THRESHOLD:
        return {
            "metric": metric,
            "today": today_value,
            "rolling_avg_7d": round(avg_value, 2),
            "ratio": round(ratio, 2),
            "direction": "spike",
            "message": f"{metric}: {today_value} today vs {round(avg_value, 1)} avg ({round(ratio, 1)}x spike)",
        }
    if ratio < _LOW_THRESHOLD:
        return {
            "metric": metric,
            "today": today_value,
            "rolling_avg_7d": round(avg_value, 2),
            "ratio": round(ratio, 2),
            "direction": "drop",
            "message": f"{metric}: {today_value} today vs {round(avg_value, 1)} avg (significant drop)",
        }
    return None
