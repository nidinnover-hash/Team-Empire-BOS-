"""Self-learning feedback loops.

Tracks which AI recommendations were applied, measures outcomes,
and feeds insights back into the learning cycle.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coaching_report import CoachingReport
from app.models.learning_outcome import LearningOutcome


async def record_outcome(
    db: AsyncSession,
    org_id: int,
    coaching_report_id: int,
    was_applied: bool,
    outcome_score: float,
    notes: str | None = None,
) -> dict[str, Any]:
    """Record whether a coaching recommendation was applied and its outcome."""
    report = (
        await db.execute(
            select(CoachingReport).where(
                CoachingReport.id == coaching_report_id,
                CoachingReport.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()

    if report is None:
        return {"ok": False, "error": "Coaching report not found"}

    recs = report.recommendations_json.get("recommendations", [])
    rec_text = recs[0].get("suggestion", "N/A") if recs else "General recommendation"

    outcome = LearningOutcome(
        organization_id=org_id,
        coaching_report_id=coaching_report_id,
        recommendation_text=rec_text[:500],
        was_applied=was_applied,
        outcome_score=outcome_score,
        notes=notes,
    )
    db.add(outcome)
    await db.commit()
    await db.refresh(outcome)

    return {"ok": True, "outcome_id": outcome.id}


async def analyze_effectiveness(
    db: AsyncSession,
    org_id: int,
    days: int = 90,
) -> dict[str, Any]:
    """Analyze which recommendation types actually improve metrics."""
    cutoff = datetime.now(UTC) - timedelta(days=max(1, days))

    total = int(
        (
            await db.execute(
                select(func.count(LearningOutcome.id)).where(
                    LearningOutcome.organization_id == org_id,
                    LearningOutcome.created_at >= cutoff,
                )
            )
        ).scalar_one() or 0
    )

    applied_count = int(
        (
            await db.execute(
                select(func.count(LearningOutcome.id)).where(
                    LearningOutcome.organization_id == org_id,
                    LearningOutcome.was_applied is True,
                    LearningOutcome.created_at >= cutoff,
                )
            )
        ).scalar_one() or 0
    )

    avg_applied = (
        await db.execute(
            select(func.avg(LearningOutcome.outcome_score)).where(
                LearningOutcome.organization_id == org_id,
                LearningOutcome.was_applied is True,
                LearningOutcome.created_at >= cutoff,
            )
        )
    ).scalar_one()

    avg_not_applied = (
        await db.execute(
            select(func.avg(LearningOutcome.outcome_score)).where(
                LearningOutcome.organization_id == org_id,
                LearningOutcome.was_applied is False,
                LearningOutcome.created_at >= cutoff,
            )
        )
    ).scalar_one()

    return {
        "window_days": days,
        "total_outcomes": total,
        "applied_count": applied_count,
        "not_applied_count": total - applied_count,
        "avg_score_when_applied": round(float(avg_applied or 0), 4),
        "avg_score_when_not_applied": round(float(avg_not_applied or 0), 4),
        "application_rate": round(applied_count / max(total, 1), 4),
    }


async def get_learning_insights(
    db: AsyncSession,
    org_id: int,
    days: int = 90,
) -> dict[str, Any]:
    """What the system has learned from coaching outcomes."""
    effectiveness = await analyze_effectiveness(db, org_id, days)

    # Count by report type
    cutoff = datetime.now(UTC) - timedelta(days=max(1, days))
    type_rows = (
        await db.execute(
            select(CoachingReport.report_type, func.count(CoachingReport.id))
            .where(
                CoachingReport.organization_id == org_id,
                CoachingReport.created_at >= cutoff,
            )
            .group_by(CoachingReport.report_type)
        )
    ).all()
    reports_by_type = {str(rt): int(cnt) for rt, cnt in type_rows}

    # Approval rate
    approved = int(
        (
            await db.execute(
                select(func.count(CoachingReport.id)).where(
                    CoachingReport.organization_id == org_id,
                    CoachingReport.status == "approved",
                    CoachingReport.created_at >= cutoff,
                )
            )
        ).scalar_one() or 0
    )
    total_reports = sum(reports_by_type.values())
    approval_rate = round(approved / max(total_reports, 1), 4)

    improvement_delta = (
        effectiveness["avg_score_when_applied"] - effectiveness["avg_score_when_not_applied"]
    )

    return {
        "effectiveness": effectiveness,
        "reports_by_type": reports_by_type,
        "total_reports": total_reports,
        "approved_reports": approved,
        "approval_rate": approval_rate,
        "improvement_delta": round(improvement_delta, 4),
        "system_learning": (
            "Applied recommendations show measurably better outcomes"
            if improvement_delta > 0.05
            else "Insufficient data to determine recommendation effectiveness"
        ),
    }
