from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.logs.audit import record_action
from app.models.approval import Approval
from app.models.email import Email
from app.models.event import Event
from app.models.governance import GovernanceViolation
from app.models.integration import Integration
from app.models.notification import Notification
from app.models.trend_telemetry_counter import TrendTelemetryCounter
from app.models.webhook import WebhookDelivery
from app.services import feature_flags
from app.services import governance as gov_service
from app.services.token_health import get_rotation_report, get_security_center

logger = logging.getLogger(__name__)

SECURITY_EVENT = "integrations_security_center_viewed"
GOVERNANCE_EVENT = "governance_policy_drift_detected"
INCIDENT_EVENT = "incident_command_mode_viewed"

_metrics: dict[str, float] = {
    "write_attempted": 0,
    "write_success": 0,
    "write_skipped_throttled": 0,
    "write_errors": 0,
    "read_requests": 0,
    "read_errors": 0,
    "read_points_returned": 0,
    "read_latency_ms_total": 0.0,
    "read_latency_samples": 0,
}


def _inc(name: str, amount: float = 1.0) -> None:
    _metrics[name] = _metrics.get(name, 0) + amount


def _as_counter_name(name: str) -> str:
    return f"trend_{name}"


async def _inc_db_metrics(db: AsyncSession, *, org_id: int, deltas: dict[str, float]) -> None:
    if not deltas:
        return

    now = datetime.now(UTC)
    for name, amount in deltas.items():
        counter_name = _as_counter_name(name)
        row = (
            (
                await db.execute(
                    select(TrendTelemetryCounter).where(
                        TrendTelemetryCounter.organization_id == org_id,
                        TrendTelemetryCounter.metric_name == counter_name,
                    )
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            db.add(
                TrendTelemetryCounter(
                    organization_id=org_id,
                    metric_name=counter_name,
                    metric_value=float(amount),
                    updated_at=now,
                )
            )
        else:
            row.metric_value = float(row.metric_value or 0.0) + float(amount)
            row.updated_at = now
    try:
        await db.commit()
    except IntegrityError:
        # Handle concurrent inserts for the same org/metric by retrying as updates.
        await db.rollback()
        for name, amount in deltas.items():
            counter_name = _as_counter_name(name)
            row = (
                (
                    await db.execute(
                        select(TrendTelemetryCounter).where(
                            TrendTelemetryCounter.organization_id == org_id,
                            TrendTelemetryCounter.metric_name == counter_name,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if row is None:
                continue
            row.metric_value = float(row.metric_value or 0.0) + float(amount)
            row.updated_at = now
        await db.commit()


async def get_trend_metrics(db: AsyncSession, *, org_id: int) -> dict[str, float]:
    stats = {
        "write_attempted": 0.0,
        "write_success": 0.0,
        "write_skipped_throttled": 0.0,
        "write_errors": 0.0,
        "read_requests": 0.0,
        "read_errors": 0.0,
        "read_points_returned": 0.0,
        "read_latency_ms_total": 0.0,
        "read_latency_samples": 0.0,
    }
    rows = (
        (
            await db.execute(
                select(TrendTelemetryCounter).where(
                    TrendTelemetryCounter.organization_id == org_id,
                    TrendTelemetryCounter.metric_name.like("trend_%"),
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        metric_key = str(row.metric_name).removeprefix("trend_")
        if metric_key in stats:
            stats[metric_key] = float(row.metric_value or 0.0)
    samples = max(1.0, float(stats.get("read_latency_samples", 0.0) or 0.0))
    stats["read_latency_ms_avg"] = round(float(stats.get("read_latency_ms_total", 0.0)) / samples, 3)
    return stats


def compute_security_risk_payload(security_center: dict[str, Any]) -> dict[str, Any]:
    summary = security_center.get("summary") if isinstance(security_center, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    risk_level = str(security_center.get("risk_level", "low")).lower() if isinstance(security_center, dict) else "low"
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "low"
    risk_base = 15 if risk_level == "low" else (40 if risk_level == "medium" else 70)
    rotation_overdue = int(summary.get("rotation_overdue", 0) or 0)
    rotation_due_soon = int(summary.get("rotation_due_soon", 0) or 0)
    manual_required = int(summary.get("manual_required", 0) or 0)
    risk_score = min(100, risk_base + rotation_overdue * 6 + rotation_due_soon * 2 + manual_required * 8)
    return {
        "risk_level": risk_level,
        "risk_score": int(risk_score),
        "rotation_overdue": rotation_overdue,
        "rotation_due_soon": rotation_due_soon,
        "manual_required": manual_required,
    }


def compute_policy_drift_payload(report: dict[str, Any], window_days: int) -> dict[str, Any]:
    signals = report.get("signals", [])
    if not isinstance(signals, list):
        signals = []
    max_drift = 0.0
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        try:
            drift_val = abs(float(signal.get("drift_percent", 0.0) or 0.0))
        except (TypeError, ValueError):
            drift_val = 0.0
        if drift_val > max_drift:
            max_drift = drift_val
    return {
        "window_days": int(window_days),
        "status": str(report.get("status", "ok")),
        "signals": len(signals),
        "max_drift_percent": round(max_drift, 3),
    }


def _to_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


async def compute_incident_snapshot(db: AsyncSession, org_id: int) -> dict[str, Any]:
    recent_cutoff = datetime.now(UTC) - timedelta(hours=24)
    pending_approvals = int(
        (
            await db.execute(
                select(func.count(Approval.id)).where(
                    Approval.organization_id == org_id,
                    Approval.status == "pending",
                )
            )
        ).scalar_one() or 0
    )
    unread_emails = int(
        (
            await db.execute(
                select(func.count(Email.id)).where(
                    Email.organization_id == org_id,
                    Email.is_read.is_(False),
                )
            )
        ).scalar_one() or 0
    )
    open_violations = int(
        (
            await db.execute(
                select(func.count(GovernanceViolation.id)).where(
                    GovernanceViolation.organization_id == org_id,
                    GovernanceViolation.status == "open",
                )
            )
        ).scalar_one() or 0
    )
    unread_high_alerts = int(
        (
            await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.organization_id == org_id,
                    Notification.is_read.is_(False),
                    Notification.severity.in_(["high", "error", "critical"]),
                )
            )
        ).scalar_one() or 0
    )
    sync_error_integrations = int(
        (
            await db.execute(
                select(func.count(Integration.id)).where(
                    Integration.organization_id == org_id,
                    Integration.sync_error_count > 0,
                )
            )
        ).scalar_one() or 0
    )
    webhook_failures_24h = int(
        (
            await db.execute(
                select(func.count(WebhookDelivery.id)).where(
                    WebhookDelivery.organization_id == org_id,
                    WebhookDelivery.created_at >= recent_cutoff,
                    WebhookDelivery.status.in_(["failed", "dead_letter"]),
                )
            )
        ).scalar_one() or 0
    )
    token = await get_rotation_report(db, org_id)
    critical_tokens = _to_int(token.get("critical"))
    warning_tokens = _to_int(token.get("warnings"))

    score = 0
    if critical_tokens > 0:
        score += 3
    if warning_tokens >= 3:
        score += 1
    if open_violations >= 5:
        score += 2
    elif open_violations > 0:
        score += 1
    if pending_approvals >= 10:
        score += 1
    if unread_emails >= 50:
        score += 1
    if unread_high_alerts > 0:
        score += 2 if unread_high_alerts >= 5 else 1
    if sync_error_integrations > 0:
        score += 2 if sync_error_integrations >= 3 else 1
    if webhook_failures_24h > 0:
        score += 2 if webhook_failures_24h >= 10 else 1

    level = "green"
    if score >= 4:
        level = "red"
    elif score >= 2:
        level = "amber"

    actions: list[str] = []
    if critical_tokens > 0:
        actions.append("Reconnect expired OAuth integrations now.")
    if warning_tokens > 0:
        actions.append("Rotate or refresh warning-state tokens within 24 hours.")
    if open_violations > 0:
        actions.append("Triages governance violations and assign owner by severity.")
    if unread_high_alerts > 0:
        actions.append("Acknowledge unread high-severity alerts and assign incident owners.")
    if sync_error_integrations > 0:
        actions.append("Repair integration sync failures and verify token health.")
    if webhook_failures_24h > 0:
        actions.append("Replay failed webhooks and inspect endpoint reliability/errors.")
    if pending_approvals > 0:
        actions.append("Clear approval queue to reduce execution latency.")
    if unread_emails > 0:
        actions.append("Prioritize unread inbox processing for blocker detection.")
    if not actions:
        actions.append("No active incident triggers. Maintain normal operating cadence.")

    return {
        "generated_at": datetime.now(UTC),
        "incident_level": level,
        "score": int(score),
        "triggers": {
            "pending_approvals": pending_approvals,
            "unread_emails": unread_emails,
            "open_governance_violations": open_violations,
            "critical_tokens": critical_tokens,
            "warning_tokens": warning_tokens,
            "unread_high_alerts": unread_high_alerts,
            "sync_error_integrations": sync_error_integrations,
            "webhook_failures_24h": webhook_failures_24h,
        },
        "top_actions": actions[:5],
        "status": "active_monitoring" if score > 0 else "stable",
    }


async def record_trend_event(
    db: AsyncSession,
    *,
    org_id: int,
    event_type: str,
    payload_json: dict[str, Any],
    actor_user_id: int | None,
    entity_type: str,
    throttle_minutes: int = 15,
) -> bool:
    _inc("write_attempted")
    metric_deltas: dict[str, float] = {"write_attempted": 1.0}
    try:
        latest = (
            (
                await db.execute(
                    select(Event)
                    .where(
                        Event.organization_id == org_id,
                        Event.event_type == event_type,
                    )
                    .order_by(Event.created_at.desc(), Event.id.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if (
            latest
            and throttle_minutes > 0
            and latest.created_at >= (datetime.now(UTC) - timedelta(minutes=throttle_minutes))
        ):
            _inc("write_skipped_throttled")
            metric_deltas["write_skipped_throttled"] = metric_deltas.get("write_skipped_throttled", 0.0) + 1.0
            return False
        await record_action(
            db=db,
            event_type=event_type,
            actor_user_id=actor_user_id,
            organization_id=org_id,
            entity_type=entity_type,
            entity_id=None,
            payload_json=payload_json,
        )
        _inc("write_success")
        metric_deltas["write_success"] = metric_deltas.get("write_success", 0.0) + 1.0
        return True
    except (SQLAlchemyError, RuntimeError, ValueError, TypeError) as exc:
        logger.warning("Trend write failed org=%s event=%s: %s", org_id, event_type, type(exc).__name__)
        _inc("write_errors")
        metric_deltas["write_errors"] = metric_deltas.get("write_errors", 0.0) + 1.0
        return False
    finally:
        try:
            await _inc_db_metrics(db, org_id=org_id, deltas=metric_deltas)
        except (SQLAlchemyError, RuntimeError, ValueError, TypeError):
            logger.debug("Trend metric persist failed for write deltas org=%s", org_id)


def parse_cursor(cursor: str | None) -> tuple[datetime, int] | None:
    if not cursor:
        return None
    raw = str(cursor).strip()
    if not raw:
        return None
    ts_part, _, id_part = raw.partition("|")
    if not id_part:
        return None
    try:
        ts = datetime.fromisoformat(ts_part.replace("Z", "+00:00"))
        cursor_id = int(id_part)
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC), cursor_id


def encode_cursor(*, created_at: datetime, event_id: int) -> str:
    ts = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
    return f"{ts.astimezone(UTC).isoformat()}|{int(event_id)}"


async def read_trend_events(
    db: AsyncSession,
    *,
    org_id: int,
    event_type: str,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[Event], str | None]:
    _inc("read_requests")
    metric_deltas: dict[str, float] = {"read_requests": 1.0}
    start = time.perf_counter()
    try:
        cursor_data = parse_cursor(cursor)
        stmt = select(Event).where(
            Event.organization_id == org_id,
            Event.event_type == event_type,
        )
        if cursor_data is not None:
            cursor_ts, cursor_id = cursor_data
            stmt = stmt.where(
                or_(
                    Event.created_at < cursor_ts,
                    and_(Event.created_at == cursor_ts, Event.id < cursor_id),
                )
            )
        rows = (
            (
                await db.execute(
                    stmt
                    .order_by(Event.created_at.desc(), Event.id.desc())
                    .limit(max(1, int(limit)) + 1)
                )
            )
            .scalars()
            .all()
        )
        has_more = len(rows) > max(1, int(limit))
        trimmed = rows[: max(1, int(limit))]
        next_cursor = None
        if has_more and trimmed:
            oldest = trimmed[-1]
            next_cursor = encode_cursor(created_at=oldest.created_at, event_id=oldest.id)
        points = list(reversed(trimmed))
        _inc("read_points_returned", float(len(points)))
        metric_deltas["read_points_returned"] = metric_deltas.get("read_points_returned", 0.0) + float(len(points))
        return points, next_cursor
    except (SQLAlchemyError, RuntimeError, ValueError, TypeError):
        _inc("read_errors")
        metric_deltas["read_errors"] = metric_deltas.get("read_errors", 0.0) + 1.0
        return [], None
    finally:
        latency_ms = (time.perf_counter() - start) * 1000.0
        _inc("read_latency_ms_total", latency_ms)
        _inc("read_latency_samples")
        metric_deltas["read_latency_ms_total"] = metric_deltas.get("read_latency_ms_total", 0.0) + latency_ms
        metric_deltas["read_latency_samples"] = metric_deltas.get("read_latency_samples", 0.0) + 1.0
        try:
            await _inc_db_metrics(db, org_id=org_id, deltas=metric_deltas)
        except (SQLAlchemyError, RuntimeError, ValueError, TypeError):
            logger.debug("Trend metric persist failed for read deltas org=%s", org_id)


async def trend_snapshots_enabled(db: AsyncSession, org_id: int) -> bool:
    return await feature_flags.is_feature_enabled(
        db,
        organization_id=org_id,
        flag_name="trend_snapshots_enabled",
    )


async def snapshot_org_trends(db: AsyncSession, org_id: int) -> dict[str, int]:
    """
    Scheduler snapshot:
    - security/incident: hourly
    - policy drift: daily
    """
    if not await trend_snapshots_enabled(db, org_id):
        return {"written": 0, "skipped": 3}
    written = 0
    skipped = 0

    security_center = await get_security_center(db, org_id)
    security_payload = compute_security_risk_payload(security_center)
    if await record_trend_event(
        db,
        org_id=org_id,
        event_type=SECURITY_EVENT,
        payload_json=security_payload,
        actor_user_id=None,
        entity_type="integration_security",
        throttle_minutes=60,
    ):
        written += 1
    else:
        skipped += 1

    drift_report = await gov_service.detect_policy_drift(db, org_id=org_id, window_days=14)
    drift_payload = compute_policy_drift_payload(drift_report, window_days=14)
    if await record_trend_event(
        db,
        org_id=org_id,
        event_type=GOVERNANCE_EVENT,
        payload_json=drift_payload,
        actor_user_id=None,
        entity_type="governance",
        throttle_minutes=24 * 60,
    ):
        written += 1
    else:
        skipped += 1

    incident = await compute_incident_snapshot(db, org_id)
    incident_payload = {
        "incident_level": str(incident.get("incident_level", "green")),
        "score": int(incident.get("score", 0) or 0),
    }
    if await record_trend_event(
        db,
        org_id=org_id,
        event_type=INCIDENT_EVENT,
        payload_json=incident_payload,
        actor_user_id=None,
        entity_type="ops_incident",
        throttle_minutes=60,
    ):
        written += 1
    else:
        skipped += 1
    return {"written": written, "skipped": skipped}
