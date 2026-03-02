"""System health — tracks errors, failures, and self-healing recommendations."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_health_log import SystemHealthLog

logger = logging.getLogger(__name__)


async def record_health_event(
    db: AsyncSession,
    category: str,
    source: str,
    message: str,
    *,
    severity: str = "warning",
    org_id: int | None = None,
    details: str | None = None,
) -> SystemHealthLog:
    """Record a system health event."""
    entry = SystemHealthLog(
        organization_id=org_id,
        category=category,
        severity=severity,
        source=source,
        message=message,
        details=details,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def get_health_summary(
    db: AsyncSession,
    org_id: int | None = None,
    days: int = 7,
) -> dict:
    """Aggregate health events by category and severity."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    query = select(
        SystemHealthLog.category,
        SystemHealthLog.severity,
        func.count(SystemHealthLog.id).label("count"),
    ).where(
        SystemHealthLog.created_at >= cutoff,
    ).group_by(SystemHealthLog.category, SystemHealthLog.severity)

    if org_id is not None:
        query = query.where(SystemHealthLog.organization_id == org_id)

    result = await db.execute(query)
    rows = result.all()

    by_category: dict[str, dict[str, int]] = {}
    total = 0
    for category, severity, count in rows:
        if category not in by_category:
            by_category[category] = {}
        by_category[category][severity] = count
        total += count

    # Overall health score (100 - penalty per issue type)
    critical = sum(v.get("critical", 0) for v in by_category.values())
    errors = sum(v.get("error", 0) for v in by_category.values())
    warnings = sum(v.get("warning", 0) for v in by_category.values())
    score = max(0, min(100, 100 - (critical * 20) - (errors * 5) - (warnings * 1)))

    return {
        "window_days": days,
        "total_events": total,
        "health_score": score,
        "by_category": by_category,
        "critical_count": critical,
        "error_count": errors,
        "warning_count": warnings,
    }


async def get_recent_events(
    db: AsyncSession,
    org_id: int | None = None,
    category: str | None = None,
    severity: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Get recent health events with optional filters."""
    query = select(SystemHealthLog).order_by(SystemHealthLog.created_at.desc())
    if org_id is not None:
        query = query.where(SystemHealthLog.organization_id == org_id)
    if category:
        query = query.where(SystemHealthLog.category == category)
    if severity:
        query = query.where(SystemHealthLog.severity == severity)
    result = await db.execute(query.limit(limit))
    return [
        {
            "id": e.id,
            "category": e.category,
            "severity": e.severity,
            "source": e.source,
            "message": e.message,
            "details": e.details,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in result.scalars().all()
    ]


async def generate_autopsy(
    db: AsyncSession,
    org_id: int | None = None,
    days: int = 7,
) -> dict:
    """Analyze failure patterns and suggest self-healing actions."""
    summary = await get_health_summary(db, org_id, days)
    recommendations: list[dict] = []

    by_cat = summary["by_category"]

    if by_cat.get("ai_fallback", {}).get("warning", 0) > 3:
        recommendations.append({
            "area": "AI Provider",
            "issue": "Frequent AI provider fallbacks detected.",
            "action": "Check primary AI provider credentials and rate limits.",
            "priority": "high",
        })
    if by_cat.get("sync_failure", {}).get("error", 0) > 2:
        recommendations.append({
            "area": "Integration Sync",
            "issue": "Repeated sync failures may indicate token expiry or API changes.",
            "action": "Verify integration tokens and check external API status.",
            "priority": "high",
        })
    if by_cat.get("api_error", {}).get("error", 0) > 5:
        recommendations.append({
            "area": "API Stability",
            "issue": "High API error rate may affect user experience.",
            "action": "Review error logs and add targeted error handling.",
            "priority": "medium",
        })
    if by_cat.get("scheduler_error", {}).get("error", 0) > 1:
        recommendations.append({
            "area": "Scheduler",
            "issue": "Scheduler errors may delay background jobs.",
            "action": "Check scheduler loop health and job timeout settings.",
            "priority": "medium",
        })
    if summary["health_score"] == 100:
        recommendations.append({
            "area": "System",
            "issue": "No issues detected.",
            "action": "System is healthy. Continue monitoring.",
            "priority": "low",
        })

    return {
        "window_days": days,
        "health_score": summary["health_score"],
        "total_events": summary["total_events"],
        "recommendations": recommendations,
        "by_category": by_cat,
    }


async def cleanup_old_health_logs(
    db: AsyncSession,
    retention_days: int = 90,
) -> int:
    """Remove health logs older than retention period."""
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await db.execute(
        delete(SystemHealthLog).where(SystemHealthLog.created_at < cutoff)
    )
    if result.rowcount:
        await db.commit()
    return result.rowcount
