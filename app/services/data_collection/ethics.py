from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy_rule import PolicyRule
from app.schemas.data_collection import (
    EthicalBoundaryReport,
    EthicalViolation,
)

# ── Ethical Boundary Layer ─────────────────────────────────────────────────────

_ETHICAL_PATTERNS: dict[str, dict[str, str | tuple[str, ...]]] = {
    "bias_discrimination": {
        "keywords": ("discriminat", "biased", "racist", "sexist", "prejudice", "unfair targeting"),
        "severity": "critical",
    },
    "privacy_violation": {
        "keywords": ("personal data", "without consent", "track user", "surveillance", "spy", "dox"),
        "severity": "high",
    },
    "misinformation": {
        "keywords": ("fake news", "disinformation", "misleading", "fabricated", "false claim"),
        "severity": "high",
    },
    "manipulation": {
        "keywords": ("manipulat", "dark pattern", "coerce", "deceive", "trick user", "exploit"),
        "severity": "high",
    },
    "harmful_content": {
        "keywords": ("hate speech", "violent", "harass", "bully", "threaten", "abuse"),
        "severity": "critical",
    },
    "transparency": {
        "keywords": ("hidden", "undisclosed", "secret tracking", "opaque", "not transparent"),
        "severity": "medium",
    },
    "consent_violation": {
        "keywords": ("without permission", "no consent", "opt-out ignored", "forced", "mandatory"),
        "severity": "high",
    },
    "accountability_gap": {
        "keywords": ("no audit", "unaccountable", "untraceable", "no oversight", "no review"),
        "severity": "medium",
    },
}


async def get_ethical_boundary_report(
    db: AsyncSession,
    org_id: int,
) -> EthicalBoundaryReport:
    from app.models.memory import DailyContext, ProfileMemory
    from app.models.note import Note

    today = date.today()
    since = today - timedelta(days=30)
    since_dt = datetime.combine(since, datetime.min.time(), tzinfo=UTC)

    notes_result = await db.execute(
        select(Note).where(
            Note.organization_id == org_id,
            Note.created_at >= since_dt,
        ).limit(300)
    )
    notes = list(notes_result.scalars().all())

    mem_result = await db.execute(
        select(ProfileMemory).where(
            ProfileMemory.organization_id == org_id,
        ).limit(500)
    )
    memories = list(mem_result.scalars().all())

    ctx_result = await db.execute(
        select(DailyContext).where(
            DailyContext.organization_id == org_id,
            DailyContext.date >= since,
        ).limit(200)
    )
    contexts = list(ctx_result.scalars().all())

    violations: list[EthicalViolation] = []

    def _check_text(text: str, source: str) -> None:
        lowered = text.lower()
        for category, meta in _ETHICAL_PATTERNS.items():
            keywords = meta["keywords"]
            hits = [kw for kw in keywords if kw in lowered]  # type: ignore[union-attr]
            if hits:
                violations.append(EthicalViolation(
                    category=category,
                    severity=str(meta["severity"]),
                    description=f"Matched: {', '.join(hits[:3])}",
                    source=source,
                ))

    for note in notes:
        _check_text(f"{note.title or ''} {note.content or ''}", f"note:{note.id}")
    for mem in memories:
        _check_text(f"{mem.key} {mem.value}", f"profile_memory:{mem.id}")
    for ctx in contexts:
        _check_text(ctx.content or "", f"daily_context:{ctx.id}")

    # Deduplicate
    seen: set[str] = set()
    unique: list[EthicalViolation] = []
    for v in violations:
        key = f"{v.category}:{v.source}"
        if key not in seen:
            seen.add(key)
            unique.append(v)
    violations = unique[:50]

    # Active guardrails
    policy_count_result = await db.execute(
        select(sa_func.count(PolicyRule.id)).where(
            PolicyRule.organization_id == org_id,
            PolicyRule.is_active.is_(True),
        )
    )
    active_guardrails = int(policy_count_result.scalar() or 0)

    # Category breakdown
    category_breakdown: dict[str, int] = {}
    for v in violations:
        category_breakdown[v.category] = category_breakdown.get(v.category, 0) + 1

    # Score
    score = 100
    for v in violations:
        if v.severity == "critical":
            score -= 20
        elif v.severity == "high":
            score -= 10
        elif v.severity == "medium":
            score -= 5
    score += min(active_guardrails * 2, 10)
    score = max(0, min(100, score))

    compliance_areas = [
        "Data privacy and consent",
        "Fair and unbiased decision-making",
        "Transparency in AI actions",
        "Content safety and moderation",
        "Accountability and audit trail",
    ]

    recommendations: list[str] = []
    if any(v.severity == "critical" for v in violations):
        recommendations.append("Critical ethical violation detected. Review and remediate immediately.")
    if category_breakdown.get("privacy_violation", 0) > 0:
        recommendations.append("Review data handling practices for privacy compliance.")
    if category_breakdown.get("bias_discrimination", 0) > 0:
        recommendations.append("Audit AI outputs for bias and discriminatory patterns.")
    if active_guardrails < 3:
        recommendations.append("Create more guardrail policies to enforce ethical boundaries.")
    if not violations:
        recommendations.append("No ethical violations detected. Ethical posture is strong.")

    return EthicalBoundaryReport(
        ethics_score=score,
        violations_found=len(violations),
        violations=violations,
        category_breakdown=category_breakdown,
        active_guardrails=active_guardrails,
        compliance_areas=compliance_areas,
        recommendations=recommendations if recommendations else ["Ethical compliance is healthy."],
    )
