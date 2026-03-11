"""Intelligence and briefing jobs — daily summaries, digests, and notifications."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import IntegrationSyncError
from app.jobs._helpers import record_job_run, scheduler_error_category
from app.models.ceo_control import SchedulerJobRun

logger = logging.getLogger(__name__)

# Per-org daily dedup state (module-level, survives across scheduler cycles).
_last_ceo_summary_date_by_org: dict[int, str] = {}
_last_pending_digest_date_by_org: dict[int, str] = {}
_last_empire_flow_digest_date_by_org: dict[int, str] = {}


def _format_briefing_summary(summary: object) -> str:
    """Render executive summary payload to readable text for daily context."""
    if isinstance(summary, str):
        return summary
    if isinstance(summary, dict):
        lines = [
            f"Total members: {summary.get('total_members', 0)}",
            f"With plans: {summary.get('members_with_plan', 0)}",
            f"Tasks today: {summary.get('total_tasks_today', 0)}",
            f"Tasks done: {summary.get('tasks_done', 0)}",
            f"Pending approvals: {summary.get('pending_approvals', 0)}",
            f"Unread emails: {summary.get('unread_emails', 0)}",
        ]
        members_without_plan = summary.get("members_without_plan", [])
        if members_without_plan:
            lines.append("Missing plan: " + ", ".join(str(n) for n in members_without_plan))
        return "\n".join(lines)
    return "No briefing data."


def _severity_rank(value: object) -> int:
    text = str(value or "").strip().upper()
    return {"CRITICAL": 0, "HIGH": 1, "MED": 2, "LOW": 3}.get(text, 4)


def _extract_top_risks(report: dict[str, object], limit: int = 5) -> list[dict[str, object]]:
    rows = report.get("violations")
    if not isinstance(rows, list):
        return []
    parsed: list[dict[str, object]] = [item for item in rows if isinstance(item, dict)]
    parsed.sort(
        key=lambda row: (
            _severity_rank(row.get("severity")),
            str(row.get("created_at") or ""),
        ),
        reverse=False,
    )
    return parsed[: max(limit, 0)]


def _format_ceo_risk_digest(
    org_id: int,
    top_risks: list[dict[str, object]],
    stale_integrations: list[dict[str, object]],
    generated_at: str,
) -> str:
    lines = [
        f"CEO Daily Risk Digest (org {org_id})",
        f"Generated: {generated_at}",
        "",
        "Top Risks:",
    ]
    if not top_risks:
        lines.append("- No open high-priority violations.")
    else:
        for item in top_risks:
            lines.append(
                f"- [{item.get('severity', 'MED')}] {item.get('title', 'Policy issue')} ({item.get('platform', 'unknown')})"
            )
    lines.append("")
    lines.append("Integration SLA Alerts:")
    if not stale_integrations:
        lines.append("- All connected integrations are within SLA.")
    else:
        for row in stale_integrations:
            age_hours = row.get("age_hours")
            suffix = f"{age_hours}h stale" if age_hours is not None else "never synced"
            status = row.get("last_sync_status") or "unknown"
            lines.append(f"- {row.get('type', 'integration')}: {suffix} (status={status})")
    lines.append("")
    lines.append("Mode: suggest_only (no auto-blocking actions)")
    return "\n".join(lines)


async def _collect_stale_integrations(
    db: AsyncSession,
    org_id: int,
) -> list[dict[str, object]]:
    from app.core.config import settings
    from app.models.integration import Integration

    cutoff = datetime.now(UTC) - timedelta(hours=int(settings.SYNC_STALE_HOURS))
    rows = (
        await db.execute(
            select(Integration).where(
                Integration.organization_id == org_id,
                Integration.status == "connected",
            )
        )
    ).scalars().all()

    alerts: list[dict[str, object]] = []
    now = datetime.now(UTC)
    for item in rows:
        if item.last_sync_status == "error":
            alerts.append({
                "type": item.type,
                "age_hours": (
                    round((now - item.last_sync_at).total_seconds() / 3600, 1)
                    if item.last_sync_at else None
                ),
                "last_sync_status": item.last_sync_status,
            })
            continue
        if item.last_sync_at is None or item.last_sync_at < cutoff:
            alerts.append({
                "type": item.type,
                "age_hours": (
                    round((now - item.last_sync_at).total_seconds() / 3600, 1)
                    if item.last_sync_at else None
                ),
                "last_sync_status": item.last_sync_status,
            })
    return alerts


async def _maybe_send_daily_ceo_slack_summary(
    db: AsyncSession,
    org_id: int,
    top_risks: list[dict[str, object]],
    stale_integrations: list[dict[str, object]],
    generated_at: str,
) -> None:
    from app.core.config import settings
    from app.services import slack_service

    channel_id = (settings.CEO_ALERTS_SLACK_CHANNEL_ID or "").strip()
    if not channel_id:
        return
    message = _format_ceo_risk_digest(
        org_id=org_id,
        top_risks=top_risks,
        stale_integrations=stale_integrations,
        generated_at=generated_at,
    )
    try:
        await slack_service.send_to_slack(db, org_id=org_id, channel_id=channel_id, text=message)
    except asyncio.CancelledError:
        raise
    except (
        SQLAlchemyError, IntegrationSyncError, TimeoutError, ConnectionError,
        RuntimeError, ValueError, TypeError, OSError, ImportError, AttributeError,
    ) as exc:
        logger.warning("Daily CEO Slack digest failed for org=%d: %s", org_id, type(exc).__name__)


async def check_morning_briefing(db: AsyncSession, org_id: int) -> None:
    """Generate daily briefing at 7-9am IST if not already created today."""
    from app.models.memory import DailyContext

    tz = ZoneInfo("Asia/Kolkata")
    local_now = datetime.now(UTC).astimezone(tz)
    if local_now.hour < 7 or local_now.hour >= 9:
        return

    today_ist = local_now.date()
    result = await db.execute(
        select(DailyContext).where(
            DailyContext.organization_id == org_id,
            DailyContext.date == today_ist,
            DailyContext.context_type == "auto_briefing",
        ).limit(1)
    )
    if result.scalar_one_or_none():
        return

    try:
        from app.schemas.memory import DailyContextCreate
        from app.services import briefing as briefing_service
        from app.services import memory as memory_service

        executive = await briefing_service.get_executive_briefing(db, org_id=org_id)
        summary = executive.get("summary") or executive.get("team_summary") or "No briefing data."
        summary_text = _format_briefing_summary(summary)

        await memory_service.add_daily_context(
            db=db,
            organization_id=org_id,
            data=DailyContextCreate(
                date=today_ist,
                context_type="auto_briefing",
                content=f"Morning auto-briefing:\n{summary_text}",
                related_to="scheduler",
            ),
        )
        # Emit notification so it appears in the dashboard signal feed
        from app.services.notification import create_notification
        await create_notification(
            db,
            organization_id=org_id,
            type="daily_briefing",
            severity="info",
            title="Daily Briefing Ready",
            message=summary_text[:300],
            source="scheduler",
            entity_type="briefing",
        )
        logger.info("Morning briefing generated for org=%d", org_id)
    except asyncio.CancelledError:
        raise
    except (
        SQLAlchemyError, IntegrationSyncError, TimeoutError, ConnectionError,
        RuntimeError, ValueError, TypeError, OSError, ImportError, AttributeError,
    ) as exc:
        logger.warning("Morning briefing failed for org=%d: %s", org_id, type(exc).__name__)


async def maybe_generate_daily_ceo_summary(db: AsyncSession, org_id: int) -> None:
    from app.core.config import settings
    from app.models.ceo_control import CEOSummary
    from app.services import compliance_engine

    tz = ZoneInfo(settings.CEO_SUMMARY_TIMEZONE)
    local_now = datetime.now(UTC).astimezone(tz)
    if local_now.hour < 9:
        return
    day_key = local_now.strftime("%Y-%m-%d")
    if _last_ceo_summary_date_by_org.get(org_id) == day_key:
        return
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    existing = (await db.execute(
        select(SchedulerJobRun).where(
            SchedulerJobRun.organization_id == org_id,
            SchedulerJobRun.job_name == "daily_ceo_summary",
            SchedulerJobRun.status == "ok",
            SchedulerJobRun.finished_at >= today_start,
        ).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        _last_ceo_summary_date_by_org[org_id] = day_key
        return
    started = datetime.now(UTC)
    report = await compliance_engine.latest_report(db, org_id)
    top_risks = _extract_top_risks(report, limit=5)
    stale_integrations = await _collect_stale_integrations(db, org_id)
    generated_at = datetime.now(UTC).isoformat()
    db.add(
        CEOSummary(
            organization_id=org_id,
            summary_json=json.dumps({
                "generated_at": generated_at,
                "report_count": report.get("count", 0),
                "top_violations": top_risks,
                "stale_integrations": stale_integrations,
            }),
            created_at=datetime.now(UTC),
        )
    )
    _last_ceo_summary_date_by_org[org_id] = day_key
    await record_job_run(
        db, org_id=org_id, job_name="daily_ceo_summary", status="ok",
        started_at=started, finished_at=datetime.now(UTC),
        details={"top_risks_count": len(top_risks), "stale_integrations_count": len(stale_integrations)},
    )
    await db.commit()
    await _maybe_send_daily_ceo_slack_summary(
        db=db, org_id=org_id, top_risks=top_risks,
        stale_integrations=stale_integrations, generated_at=generated_at,
    )


async def maybe_generate_daily_pending_digest(db: AsyncSession, org_id: int) -> None:
    from app.core.config import settings
    from app.services import email_control

    if not settings.EMAIL_CONTROL_DIGEST_ENABLED:
        return
    tz = ZoneInfo("Asia/Kolkata")
    local_now = datetime.now(UTC).astimezone(tz)
    if local_now.hour < settings.EMAIL_CONTROL_DIGEST_HOUR_IST:
        return
    if (
        local_now.hour == settings.EMAIL_CONTROL_DIGEST_HOUR_IST
        and local_now.minute < settings.EMAIL_CONTROL_DIGEST_MINUTE_IST
    ):
        return
    day_key = local_now.strftime("%Y-%m-%d")
    if _last_pending_digest_date_by_org.get(org_id) == day_key:
        return
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    existing_digest = (await db.execute(
        select(SchedulerJobRun).where(
            SchedulerJobRun.organization_id == org_id,
            SchedulerJobRun.job_name == "daily_pending_digest",
            SchedulerJobRun.status == "ok",
            SchedulerJobRun.finished_at >= today_start,
        ).limit(1)
    )).scalar_one_or_none()
    if existing_digest is not None:
        _last_pending_digest_date_by_org[org_id] = day_key
        return
    from app.models.user import User
    _adm = (await db.execute(
        select(User).where(
            User.organization_id == org_id,
            User.role.in_(["CEO", "ADMIN"]),
            User.is_active.is_(True),
        ).order_by(User.id).limit(1)
    )).scalar_one_or_none()
    started_digest = datetime.now(UTC)
    await email_control.draft_pending_actions_digest_email(
        db=db, org_id=org_id,
        actor_user_id=int(_adm.id) if _adm else None,  # type: ignore[arg-type]
    )
    _last_pending_digest_date_by_org[org_id] = day_key
    await record_job_run(
        db, org_id=org_id, job_name="daily_pending_digest", status="ok",
        started_at=started_digest, finished_at=datetime.now(UTC),
    )
    await db.commit()


async def maybe_generate_daily_empire_flow_digest(db: AsyncSession, org_id: int) -> None:
    from app.core.lead_routing import EMPIRE_DIGITAL_COMPANY_ID
    from app.logs.audit import record_action
    from app.models.user import User
    from app.services import empire_digital as empire_digital_service
    from app.services.notification import create_notification

    if int(org_id) != EMPIRE_DIGITAL_COMPANY_ID:
        return
    tz = ZoneInfo("Asia/Kolkata")
    local_now = datetime.now(UTC).astimezone(tz)
    if local_now.hour < 9 or (local_now.hour == 9 and local_now.minute < 15):
        return
    day_key = local_now.strftime("%Y-%m-%d")
    if _last_empire_flow_digest_date_by_org.get(org_id) == day_key:
        return
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    existing = (await db.execute(
        select(SchedulerJobRun).where(
            SchedulerJobRun.organization_id == org_id,
            SchedulerJobRun.job_name == "daily_empire_flow_digest",
            SchedulerJobRun.status == "ok",
            SchedulerJobRun.finished_at >= today_start,
        ).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        _last_empire_flow_digest_date_by_org[org_id] = day_key
        return

    started = datetime.now(UTC)
    report = await empire_digital_service.build_founder_flow_report(
        db, actor_org_id=org_id, actor_role="CEO", window_days=1,
    )
    sla_cfg = await empire_digital_service.get_empire_sla_config(db, organization_id=org_id)
    stale_threshold = int(sla_cfg.warning_stale_count)
    today_point = report.points[-1] if report.points else None
    stale_unrouted = int(getattr(today_point, "stale_unrouted", 0))

    actor = (await db.execute(
        select(User).where(
            User.organization_id == org_id,
            User.role.in_(["CEO", "ADMIN"]),
            User.is_active.is_(True),
        ).order_by(User.id).limit(1)
    )).scalar_one_or_none()
    actor_user_id = int(actor.id) if actor else None

    escalated_ids: list[int] = []
    if stale_unrouted >= stale_threshold:
        escalated_ids = await empire_digital_service.escalate_stale_leads(
            db, actor_org_id=org_id, actor_role="CEO",
            actor_user_id=actor_user_id, contact_ids=None,
            limit=max(stale_threshold, 20),
        )
        await create_notification(
            db, organization_id=org_id, type="empire_lead_flow_alert",
            severity="warning", title="Empire lead flow stale threshold breached",
            message=(
                f"Stale unrouted leads: {stale_unrouted} "
                f"(threshold {stale_threshold}). Escalations created: {len(escalated_ids)}."
            ),
            source="sync_scheduler", entity_type="lead_flow",
        )
        await record_action(
            db, event_type="daily_empire_flow_escalation",
            actor_user_id=actor_user_id, organization_id=org_id,
            entity_type="decision_card", entity_id=None,
            payload_json={
                "stale_unrouted": stale_unrouted,
                "stale_threshold": stale_threshold,
                "escalations_created": len(escalated_ids),
            },
        )

    _last_empire_flow_digest_date_by_org[org_id] = day_key
    await record_job_run(
        db, org_id=org_id, job_name="daily_empire_flow_digest", status="ok",
        started_at=started, finished_at=datetime.now(UTC),
        details={
            "stale_unrouted": stale_unrouted,
            "stale_threshold": stale_threshold,
            "escalations_created": len(escalated_ids),
        },
    )
    await db.commit()


async def maybe_run_knowledge_consolidation(db: AsyncSession, org_id: int) -> None:
    """Nightly knowledge consolidation: merge duplicate memories, backfill embeddings, extract knowledge."""
    tz = ZoneInfo("Asia/Kolkata")
    local_now = datetime.now(UTC).astimezone(tz)
    # Run between 2-3 AM IST (low activity window)
    if local_now.hour != 2:
        return

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    existing = (await db.execute(
        select(SchedulerJobRun).where(
            SchedulerJobRun.organization_id == org_id,
            SchedulerJobRun.job_name == "knowledge_consolidation",
            SchedulerJobRun.status == "ok",
            SchedulerJobRun.finished_at >= today_start,
        ).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        return

    started = datetime.now(UTC)
    details: dict[str, object] = {}
    try:
        # 1. Consolidate duplicate memories
        from app.engines.intelligence.knowledge import consolidate_memories
        consolidation = await consolidate_memories(db, organization_id=org_id)
        details["consolidation"] = dict(consolidation)
        logger.info(
            "Knowledge consolidation org=%d: scanned=%d merged=%d deleted=%d",
            org_id, consolidation["scanned"], consolidation["merged"], consolidation["deleted"],
        )

        # 2. Backfill embeddings for entries without them
        from app.services.embedding import backfill_embeddings
        backfill = await backfill_embeddings(db, organization_id=org_id, batch_size=50)
        details["backfill"] = backfill
        logger.info("Embedding backfill org=%d: %s", org_id, backfill)

        # 3. Decay old clone memories
        from app.services.clone_memory import decay_old_memories
        decayed = await decay_old_memories(db, org_id=org_id, days_since_retrieval=90)
        details["decayed_memories"] = decayed

        await record_job_run(
            db, org_id=org_id, job_name="knowledge_consolidation", status="ok",
            started_at=started, finished_at=datetime.now(UTC), details=details,
        )
        await db.commit()
    except asyncio.CancelledError:
        raise
    except (
        SQLAlchemyError, IntegrationSyncError, TimeoutError, ConnectionError,
        RuntimeError, ValueError, TypeError, OSError, ImportError, AttributeError,
    ) as exc:
        logger.warning(
            "Knowledge consolidation failed org=%d category=%s",
            org_id, scheduler_error_category(exc), exc_info=True,
        )
        await record_job_run(
            db, org_id=org_id, job_name="knowledge_consolidation", status="error",
            started_at=started, finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        try:
            await db.commit()
        except Exception:
            await db.rollback()


async def maybe_run_weekly_coaching(db: AsyncSession, org_id: int) -> None:
    """Weekly coaching report generation — runs on Mondays at 10 AM IST.

    Auto-generates org-level coaching report if none generated this week.
    Also re-scores contacts for contact intelligence.
    """
    tz = ZoneInfo("Asia/Kolkata")
    local_now = datetime.now(UTC).astimezone(tz)
    # Only run on Mondays between 10-11 AM IST
    if local_now.weekday() != 0 or local_now.hour != 10:
        return

    # Dedup: check if already ran this week
    week_start = datetime.now(UTC) - timedelta(days=local_now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    existing = (await db.execute(
        select(SchedulerJobRun).where(
            SchedulerJobRun.organization_id == org_id,
            SchedulerJobRun.job_name == "weekly_coaching",
            SchedulerJobRun.status == "ok",
            SchedulerJobRun.finished_at >= week_start,
        ).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        return

    started = datetime.now(UTC)
    details: dict[str, object] = {}
    try:
        # 1. Generate org-level coaching report
        from app.services import ai_coaching
        result = await ai_coaching.generate_org_improvement_plan(db, org_id=org_id)
        details["coaching_report_id"] = result.get("report_id")
        details["coaching_status"] = result.get("status")

        # 2. Re-score contacts
        from app.services.contact_intelligence import batch_score_contacts
        score_result = await batch_score_contacts(db, organization_id=org_id)
        details["contacts_scored"] = score_result.get("total_scored", 0)
        details["contacts_updated"] = score_result.get("updated", 0)

        await record_job_run(
            db, org_id=org_id, job_name="weekly_coaching", status="ok",
            started_at=started, finished_at=datetime.now(UTC), details=details,
        )
        await db.commit()
        logger.info("Weekly coaching completed org=%d: %s", org_id, details)
    except asyncio.CancelledError:
        raise
    except (
        SQLAlchemyError, IntegrationSyncError, TimeoutError, ConnectionError,
        RuntimeError, ValueError, TypeError, OSError, ImportError, AttributeError,
    ) as exc:
        logger.warning(
            "Weekly coaching failed org=%d category=%s",
            org_id, scheduler_error_category(exc), exc_info=True,
        )
        await record_job_run(
            db, org_id=org_id, job_name="weekly_coaching", status="error",
            started_at=started, finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        try:
            await db.commit()
        except Exception:
            await db.rollback()


async def maybe_emit_daily_briefing_notification(db: AsyncSession, org_id: int) -> None:
    """Create a daily briefing notification with team summary (once per day per org)."""
    from app.services.notification import create_notification

    today_str = str(datetime.now(UTC).date())
    if _last_ceo_summary_date_by_org.get(org_id) == today_str:
        return

    started = datetime.now(UTC)
    try:
        from app.services.briefing import get_team_dashboard

        dashboard = await get_team_dashboard(db, org_id)
        summary = dashboard.get("summary", {})
        msg_parts = [
            f"Team: {summary.get('total_members', 0)} members",
            f"Tasks today: {summary.get('total_tasks_today', 0)}",
            f"Done: {summary.get('tasks_done', 0)}",
            f"Pending approvals: {summary.get('pending_approvals', 0)}",
            f"Unread emails: {summary.get('unread_emails', 0)}",
        ]
        no_plan = summary.get("members_without_plan", [])
        if no_plan:
            msg_parts.append(f"Missing plans: {', '.join(str(n) for n in no_plan[:5])}")

        await create_notification(
            db, organization_id=org_id, type="daily_briefing",
            severity="info", title=f"Daily Briefing — {today_str}",
            message=". ".join(msg_parts) + ".", source="scheduler",
        )
        await db.commit()
        await record_job_run(
            db, org_id=org_id, job_name="daily_briefing_notification", status="ok",
            started_at=started, finished_at=datetime.now(UTC),
        )
        await db.commit()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Daily briefing notification failed org=%d category=%s",
            org_id, scheduler_error_category(exc), exc_info=True,
        )
        await record_job_run(
            db, org_id=org_id, job_name="daily_briefing_notification", status="error",
            started_at=started, finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        await db.commit()


# Per-org daily dedup for briefing email.
_last_briefing_email_date_by_org: dict[int, str] = {}


async def maybe_send_daily_briefing_email(db: AsyncSession, org_id: int) -> None:
    """Send a morning briefing email via Gmail at 8-9am IST (once per day per org)."""
    from app.models.user import User
    from app.services.integration import get_integration_by_type

    tz = ZoneInfo("Asia/Kolkata")
    local_now = datetime.now(UTC).astimezone(tz)
    if local_now.hour < 8 or local_now.hour >= 9:
        return

    day_key = local_now.strftime("%Y-%m-%d")
    if _last_briefing_email_date_by_org.get(org_id) == day_key:
        return

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    existing = (await db.execute(
        select(SchedulerJobRun).where(
            SchedulerJobRun.organization_id == org_id,
            SchedulerJobRun.job_name == "daily_briefing_email",
            SchedulerJobRun.status == "ok",
            SchedulerJobRun.finished_at >= today_start,
        ).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        _last_briefing_email_date_by_org[org_id] = day_key
        return

    # Find admin email
    admin = (await db.execute(
        select(User).where(
            User.organization_id == org_id,
            User.role.in_(["CEO", "ADMIN"]),
            User.is_active.is_(True),
        ).order_by(User.id).limit(1)
    )).scalar_one_or_none()
    if admin is None:
        return

    # Check Gmail integration
    integration = await get_integration_by_type(db, org_id, "gmail")
    if not integration:
        return

    started = datetime.now(UTC)
    try:
        from app.services.briefing import get_executive_briefing

        executive = await get_executive_briefing(db, org_id=org_id)
        summary = executive.get("summary") or executive.get("team_summary") or {}
        briefing_text = _format_briefing_summary(summary)

        calendar = executive.get("calendar", {})
        cal_count = calendar.get("event_count", 0)
        cal_events = calendar.get("events", [])
        cal_lines = "\n".join(
            f"  - {e.get('content', 'Event')}" for e in cal_events[:5]
        ) if cal_events else "  No events today."

        approvals = executive.get("approvals", {})
        pending = approvals.get("pending_count", 0)

        inbox = executive.get("inbox", {})
        unread = inbox.get("unread_count", 0)

        priorities = executive.get("today_priorities", [])
        priority_lines = "\n".join(
            f"  {i+1}. {p}" for i, p in enumerate(priorities[:5])
        ) if priorities else "  None set."

        subject = f"Morning Briefing — {day_key}"
        body = (
            f"Good morning.\n\n"
            f"TEAM STATUS\n{briefing_text}\n\n"
            f"CALENDAR ({cal_count} events)\n{cal_lines}\n\n"
            f"PENDING APPROVALS: {pending}\n"
            f"UNREAD EMAILS: {unread}\n\n"
            f"TODAY'S PRIORITIES\n{priority_lines}\n\n"
            f"— Nidin BOS"
        )

        config = integration.config_json or {}
        access_token = config.get("access_token", "")
        refresh_token = config.get("refresh_token")
        expires_at = config.get("expires_at")

        from app.tools import gmail as gmail_tool
        sent = await asyncio.to_thread(
            gmail_tool.send_email,
            access_token=access_token,
            to=admin.email,
            subject=subject,
            body=body,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

        _last_briefing_email_date_by_org[org_id] = day_key
        await record_job_run(
            db, org_id=org_id, job_name="daily_briefing_email",
            status="ok" if sent else "error",
            started_at=started, finished_at=datetime.now(UTC),
            details={"to": admin.email, "sent": sent},
        )
        await db.commit()
        logger.info("Daily briefing email org=%d sent=%s", org_id, sent)
    except asyncio.CancelledError:
        raise
    except (
        SQLAlchemyError, IntegrationSyncError, TimeoutError, ConnectionError,
        RuntimeError, ValueError, TypeError, OSError, ImportError, AttributeError,
    ) as exc:
        logger.warning(
            "Daily briefing email failed org=%d: %s",
            org_id, scheduler_error_category(exc), exc_info=True,
        )
        await record_job_run(
            db, org_id=org_id, job_name="daily_briefing_email", status="error",
            started_at=started, finished_at=datetime.now(UTC),
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        try:
            await db.commit()
        except Exception:
            await db.rollback()
