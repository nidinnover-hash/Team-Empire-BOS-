"""Policy effectiveness — tracks whether policies actually improve behavior."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.governance import GovernancePolicy, GovernanceViolation

logger = logging.getLogger(__name__)


async def get_policy_effectiveness(
    db: AsyncSession,
    org_id: int,
    weeks: int = 8,
) -> dict:
    """Measure per-policy violation trends and recommend adjustments."""
    cutoff = datetime.now(UTC) - timedelta(weeks=weeks)

    policies_result = await db.execute(
        select(GovernancePolicy).where(
            GovernancePolicy.organization_id == org_id,
            GovernancePolicy.is_active.is_(True),
        )
    )
    policies = list(policies_result.scalars().all())

    if not policies:
        return {
            "policies_analyzed": 0,
            "reports": [],
            "recommendations": [],
            "summary": "No active policies found.",
        }

    reports: list[dict] = []
    recommendations: list[dict] = []

    for policy in policies:
        # Get weekly violation counts
        violations_result = await db.execute(
            select(GovernanceViolation).where(
                GovernanceViolation.policy_id == policy.id,
                GovernanceViolation.created_at >= cutoff,
            ).order_by(GovernanceViolation.created_at)
        )
        violations = list(violations_result.scalars().all())
        total = len(violations)
        open_count = sum(1 for v in violations if v.status == "open")
        resolved_count = sum(1 for v in violations if v.status == "resolved")
        dismissed_count = sum(1 for v in violations if v.status == "dismissed")

        # Split into first half vs second half to detect trend
        if total >= 4:
            midpoint = total // 2
            first_half = violations[:midpoint]
            second_half = violations[midpoint:]
            trend = "improving" if len(second_half) < len(first_half) else (
                "stable" if len(second_half) == len(first_half) else "worsening"
            )
        else:
            trend = "insufficient_data"

        effectiveness = "effective" if trend == "improving" else (
            "neutral" if trend in ("stable", "insufficient_data") else "ineffective"
        )

        report = {
            "policy_id": policy.id,
            "policy_name": policy.name,
            "policy_type": policy.policy_type,
            "total_violations": total,
            "open": open_count,
            "resolved": resolved_count,
            "dismissed": dismissed_count,
            "trend": trend,
            "effectiveness": effectiveness,
        }
        reports.append(report)

        # Generate recommendations
        if trend == "worsening" and total >= 4:
            recommendations.append({
                "policy_id": policy.id,
                "policy_name": policy.name,
                "recommendation": "tighten",
                "reason": f"Violation rate increased from {len(first_half)} to {len(second_half)} in {weeks}-week window.",
                "priority": "high",
                "action": "Review policy rules and consider stricter thresholds or additional enforcement.",
            })
        elif total == 0 and weeks >= 8:
            recommendations.append({
                "policy_id": policy.id,
                "policy_name": policy.name,
                "recommendation": "graduate",
                "reason": f"Zero violations for {weeks} weeks — behavior is embedded.",
                "priority": "low",
                "action": "Consider graduating this policy to 'embedded' status and reducing check frequency.",
            })
        elif dismissed_count > resolved_count and total >= 3:
            recommendations.append({
                "policy_id": policy.id,
                "policy_name": policy.name,
                "recommendation": "review_relevance",
                "reason": f"More dismissed ({dismissed_count}) than resolved ({resolved_count}) — policy may be too strict.",
                "priority": "medium",
                "action": "Review policy rules for relevance. Consider loosening thresholds.",
            })

    effective_count = sum(1 for r in reports if r["effectiveness"] == "effective")
    ineffective_count = sum(1 for r in reports if r["effectiveness"] == "ineffective")

    return {
        "policies_analyzed": len(reports),
        "effective_policies": effective_count,
        "ineffective_policies": ineffective_count,
        "reports": reports,
        "recommendations": recommendations,
        "summary": (
            f"{effective_count}/{len(reports)} policies improving behavior. "
            f"{len(recommendations)} recommendations generated."
        ),
    }


async def get_violation_rate_trend(
    db: AsyncSession,
    org_id: int,
    policy_id: int,
    weeks: int = 12,
) -> list[dict]:
    """Get weekly violation count trend for a specific policy."""
    cutoff = datetime.now(UTC) - timedelta(weeks=weeks)
    result = await db.execute(
        select(
            func.date(GovernanceViolation.created_at).label("week"),
            func.count(GovernanceViolation.id).label("count"),
        ).where(
            GovernanceViolation.policy_id == policy_id,
            GovernanceViolation.created_at >= cutoff,
        ).group_by(func.date(GovernanceViolation.created_at))
        .order_by(func.date(GovernanceViolation.created_at))
    )
    return [{"date": str(row.week), "violations": row.count} for row in result.all()]
