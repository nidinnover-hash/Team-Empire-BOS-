from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy_rule import PolicyRule
from app.models.threat_signal import ThreatSignal
from app.schemas.data_collection import (
    ThreatDetectionResult,
    ThreatLayerReport,
    ThreatSignalOut,
    ThreatTrainRequest,
    ThreatTrainResult,
)
from app.services import memory as memory_service

# ── Digital Threat Detection ───────────────────────────────────────────────────

_THREAT_PATTERNS: dict[str, dict[str, str | tuple[str, ...]]] = {
    "credential_leak": {
        "keywords": ("password", "secret", "token", "api_key", "apikey", "credentials", "private_key"),
        "severity": "critical",
        "title": "Potential credential exposure detected",
    },
    "injection_attempt": {
        "keywords": ("' or ", "1=1", "<script", "eval(", "exec(", "drop table", "union select"),
        "severity": "high",
        "title": "Injection pattern detected in input",
    },
    "rate_abuse": {
        "keywords": ("rate limit", "too many requests", "429", "throttled", "brute force"),
        "severity": "medium",
        "title": "Rate abuse or brute-force indicator",
    },
    "privilege_escalation": {
        "keywords": ("admin", "sudo", "force_role", "escalat", "bypass", "override"),
        "severity": "high",
        "title": "Privilege escalation pattern detected",
    },
    "data_exfiltration": {
        "keywords": ("export all", "bulk download", "dump", "extract", "scrape", "exfil"),
        "severity": "high",
        "title": "Data exfiltration risk detected",
    },
    "suspicious_pattern": {
        "keywords": ("suspicious", "anomaly", "unusual", "unexpected", "unauthorized"),
        "severity": "medium",
        "title": "Suspicious behavioral pattern detected",
    },
    "config_weakness": {
        "keywords": ("debug=true", "debug mode", "verbose", "permissive", "cors *", "allow all"),
        "severity": "low",
        "title": "Configuration weakness identified",
    },
    "dependency_risk": {
        "keywords": ("vulnerable", "cve-", "deprecated", "outdated", "end of life", "eol"),
        "severity": "medium",
        "title": "Dependency or version risk detected",
    },
}


def _scan_text_for_threats(text: str) -> list[dict[str, str]]:
    lowered = text.lower()
    found: list[dict[str, str]] = []
    for category, meta in _THREAT_PATTERNS.items():
        keywords = meta["keywords"]
        hits = [kw for kw in keywords if kw in lowered]  # type: ignore[union-attr]
        if hits:
            found.append({
                "category": category,
                "severity": str(meta["severity"]),
                "title": str(meta["title"]),
                "description": f"Matched patterns: {', '.join(hits[:5])}",
            })
    return found


async def detect_threats(
    db: AsyncSession,
    org_id: int,
    scope: str = "full_scan",
) -> ThreatDetectionResult:
    from app.models.memory import DailyContext, ProfileMemory
    from app.models.note import Note

    today = date.today()
    since = today - timedelta(days=7)

    # Scan recent notes
    notes_result = await db.execute(
        select(Note).where(
            Note.organization_id == org_id,
            Note.created_at >= datetime.combine(since, datetime.min.time(), tzinfo=UTC),
        ).limit(200)
    )
    notes = list(notes_result.scalars().all())

    # Scan recent daily context
    ctx_result = await db.execute(
        select(DailyContext).where(
            DailyContext.organization_id == org_id,
            DailyContext.date >= since,
        ).limit(200)
    )
    contexts = list(ctx_result.scalars().all())

    # Scan profile memory
    mem_result = await db.execute(
        select(ProfileMemory).where(
            ProfileMemory.organization_id == org_id,
        ).limit(500)
    )
    memories = list(mem_result.scalars().all())

    all_signals: list[dict[str, str]] = []
    scanned_sources: list[tuple[str, str]] = []

    for note in notes:
        text = f"{note.title or ''} {note.content or ''}"
        scanned_sources.append(("note", str(note.id)))
        for sig in _scan_text_for_threats(text):
            sig["source"] = f"note:{note.id}"
            all_signals.append(sig)

    for ctx in contexts:
        scanned_sources.append(("daily_context", str(ctx.id)))
        for sig in _scan_text_for_threats(ctx.content or ""):
            sig["source"] = f"daily_context:{ctx.id}"
            all_signals.append(sig)

    for mem in memories:
        scanned_sources.append(("profile_memory", str(mem.id)))
        for sig in _scan_text_for_threats(f"{mem.key} {mem.value}"):
            sig["source"] = f"profile_memory:{mem.id}"
            all_signals.append(sig)

    # Deduplicate by category+source
    seen: set[str] = set()
    unique_signals: list[dict[str, str]] = []
    for sig in all_signals:
        key = f"{sig['category']}:{sig['source']}"
        if key not in seen:
            seen.add(key)
            unique_signals.append(sig)

    # Create ThreatSignal records and policy drafts
    signal_records: list[ThreatSignalOut] = []
    policy_drafts_created = 0

    for sig in unique_signals[:50]:
        can_auto_mitigate = sig["severity"] in ("low", "info")
        ts = ThreatSignal(
            organization_id=org_id,
            category=sig["category"],
            severity=sig["severity"],
            title=sig["title"],
            description=sig["description"][:500],
            source=sig["source"][:80],
            auto_mitigated=can_auto_mitigate,
        )
        db.add(ts)
        await db.flush()

        if sig["severity"] in ("critical", "high"):
            policy = PolicyRule(
                organization_id=org_id,
                title=f"Threat Guard: {sig['category'].replace('_', ' ').title()}",
                rule_text=(
                    f"Auto-generated from threat detection. "
                    f"Block or flag content matching '{sig['category']}' patterns. "
                    f"Source: {sig['source']}."
                ),
                examples_json=json.dumps([sig["description"][:200]]),
                is_active=False,
            )
            db.add(policy)
            await db.flush()
            ts.policy_rule_id = int(policy.id)
            policy_drafts_created += 1

        signal_records.append(ThreatSignalOut(
            id=int(ts.id),
            category=ts.category,
            severity=ts.severity,
            title=ts.title,
            description=ts.description,
            source=ts.source,
            auto_mitigated=ts.auto_mitigated,
            created_at=ts.created_at.isoformat() if ts.created_at else "",
        ))

    await db.commit()

    severity_breakdown: dict[str, int] = {}
    out_sig: ThreatSignalOut
    for out_sig in signal_records:
        severity_breakdown[out_sig.severity] = severity_breakdown.get(out_sig.severity, 0) + 1

    return ThreatDetectionResult(
        scope=scope,
        signals_found=len(signal_records),
        signals=signal_records,
        severity_breakdown=severity_breakdown,
        policy_drafts_created=policy_drafts_created,
        message=f"Threat scan completed. {len(signal_records)} signal(s) detected across {len(scanned_sources)} items.",
    )


async def train_threat_signals(
    db: AsyncSession,
    org_id: int,
    data: ThreatTrainRequest,
) -> ThreatTrainResult:
    result = await db.execute(
        select(ThreatSignal).where(
            ThreatSignal.organization_id == org_id,
            ThreatSignal.id.in_(data.signal_ids),
        )
    )
    signals = list(result.scalars().all())
    if not signals:
        raise ValueError("No matching threat signals found for this organization")

    policies_activated = 0
    policies_dismissed = 0
    memory_keys: list[str] = []
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")

    for sig in signals:
        if data.action == "approve":
            # Activate associated policy if exists
            if sig.policy_rule_id:
                policy_result = await db.execute(
                    select(PolicyRule).where(PolicyRule.id == sig.policy_rule_id)
                )
                policy = policy_result.scalar_one_or_none()
                if policy and not policy.is_active:
                    policy.is_active = True
                    policies_activated += 1

            # Feed into memory for self-training
            key = f"threat.learned.{sig.category}.{stamp}"
            await memory_service.upsert_profile_memory(
                db=db,
                organization_id=org_id,
                key=key[:100],
                value=f"Confirmed threat pattern: {sig.title} - {sig.description[:150]}",
                category="threat_intelligence",
            )
            memory_keys.append(key[:100])
        else:
            sig.dismissed = True
            if sig.policy_rule_id:
                policy_result = await db.execute(
                    select(PolicyRule).where(PolicyRule.id == sig.policy_rule_id)
                )
                policy = policy_result.scalar_one_or_none()
                if policy:
                    policy.is_active = False
                    policies_dismissed += 1

    await db.commit()

    return ThreatTrainResult(
        processed=len(signals),
        policies_activated=policies_activated,
        policies_dismissed=policies_dismissed,
        memory_keys=memory_keys,
        message=(
            f"Processed {len(signals)} signal(s). "
            f"{policies_activated} policies activated, {policies_dismissed} dismissed. "
            "Clone security intelligence updated."
        ),
    )


async def get_threat_layer_report(
    db: AsyncSession,
    org_id: int,
) -> ThreatLayerReport:
    today = date.today()
    since = today - timedelta(days=7)
    since_dt = datetime.combine(since, datetime.min.time(), tzinfo=UTC)

    # Count signals in last 7 days
    signals_result = await db.execute(
        select(ThreatSignal).where(
            ThreatSignal.organization_id == org_id,
            ThreatSignal.created_at >= since_dt,
        ).order_by(ThreatSignal.created_at.desc()).limit(100)
    )
    signals = list(signals_result.scalars().all())

    severity_breakdown: dict[str, int] = {}
    auto_mitigated = 0
    for sig in signals:
        severity_breakdown[sig.severity] = severity_breakdown.get(sig.severity, 0) + 1
        if sig.auto_mitigated:
            auto_mitigated += 1

    # Active policies
    policy_count_result = await db.execute(
        select(sa_func.count(PolicyRule.id)).where(
            PolicyRule.organization_id == org_id,
            PolicyRule.is_active.is_(True),
        )
    )
    active_policies = int(policy_count_result.scalar() or 0)

    # Score: start at 100, deduct for severity
    score = 100
    score -= severity_breakdown.get("critical", 0) * 20
    score -= severity_breakdown.get("high", 0) * 10
    score -= severity_breakdown.get("medium", 0) * 5
    score -= severity_breakdown.get("low", 0) * 2
    score += min(active_policies * 3, 15)  # Bonus for active policies
    score += min(auto_mitigated * 2, 10)   # Bonus for auto-mitigation
    score = max(0, min(100, score))

    # Top threats
    top_signals = sorted(
        [s for s in signals if not s.dismissed],
        key=lambda s: {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}.get(s.severity, 0),
        reverse=True,
    )[:5]

    top_threats = [
        ThreatSignalOut(
            id=int(s.id),
            category=s.category,
            severity=s.severity,
            title=s.title,
            description=s.description,
            source=s.source,
            auto_mitigated=s.auto_mitigated,
            created_at=s.created_at.isoformat() if s.created_at else "",
        )
        for s in top_signals
    ]

    recommendations: list[str] = []
    if severity_breakdown.get("critical", 0) > 0:
        recommendations.append("Immediately review and remediate critical threat signals.")
    if severity_breakdown.get("high", 0) > 2:
        recommendations.append("Multiple high-severity threats detected. Run a focused security audit.")
    if active_policies < 3:
        recommendations.append("Activate more security policies to improve automated protection.")
    if not signals:
        recommendations.append("No threats detected in the last 7 days. Continue regular scans.")
    if auto_mitigated < len(signals) // 2 and signals:
        recommendations.append("Increase auto-mitigation coverage by training on confirmed threats.")

    return ThreatLayerReport(
        security_score=score,
        total_signals_7d=len(signals),
        severity_breakdown=severity_breakdown,
        top_threats=top_threats,
        active_policies=active_policies,
        auto_mitigated_count=auto_mitigated,
        recommendations=recommendations if recommendations else ["Security posture is healthy."],
    )
