from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy_rule import PolicyRule
from app.schemas.data_collection import (
    FraudDetectionResult,
    FraudLayerReport,
    FraudSignalOut,
)

# ── Fraud Detection ────────────────────────────────────────────────────────────

_FRAUD_PATTERNS: dict[str, dict[str, str | tuple[str, ...]]] = {
    "financial_anomaly": {
        "keywords": ("unusual amount", "large transfer", "unexpected charge", "abnormal", "spike"),
        "severity": "high",
        "title": "Financial anomaly detected",
    },
    "duplicate_transaction": {
        "keywords": ("duplicate", "double charge", "repeated payment", "same amount twice"),
        "severity": "medium",
        "title": "Possible duplicate transaction",
    },
    "invoice_fraud": {
        "keywords": ("fake invoice", "inflated", "overcharged", "phantom invoice", "forged"),
        "severity": "high",
        "title": "Invoice fraud indicator",
    },
    "expense_fraud": {
        "keywords": ("personal expense", "unauthorized purchase", "expense padding", "receipt"),
        "severity": "medium",
        "title": "Expense fraud indicator",
    },
    "phantom_vendor": {
        "keywords": ("unknown vendor", "shell company", "no contract", "unregistered", "fictitious"),
        "severity": "high",
        "title": "Phantom vendor risk",
    },
    "identity_fraud": {
        "keywords": ("impersonat", "fake identity", "stolen identity", "spoofed", "phishing"),
        "severity": "critical",
        "title": "Identity fraud detected",
    },
    "unauthorized_access": {
        "keywords": ("unauthorized", "breach", "illegal access", "hacked", "compromised"),
        "severity": "critical",
        "title": "Unauthorized access detected",
    },
    "data_tampering": {
        "keywords": ("tamper", "altered record", "modified without", "forged data", "falsified"),
        "severity": "high",
        "title": "Data tampering indicator",
    },
}


def _scan_for_fraud(text: str) -> list[dict[str, str | int]]:
    lowered = text.lower()
    found: list[dict[str, str | int]] = []
    for category, meta in _FRAUD_PATTERNS.items():
        keywords = meta["keywords"]
        hits = [kw for kw in keywords if kw in lowered]  # type: ignore[union-attr]
        if hits:
            risk_score = 70
            if meta["severity"] == "critical":
                risk_score = 95
            elif meta["severity"] == "high":
                risk_score = 80
            elif meta["severity"] == "medium":
                risk_score = 60
            found.append({
                "category": category,
                "severity": str(meta["severity"]),
                "title": str(meta["title"]),
                "description": f"Matched fraud patterns: {', '.join(hits[:5])}",
                "risk_score": risk_score,
            })
    return found


async def detect_fraud(
    db: AsyncSession,
    org_id: int,
    scope: str = "full_scan",
) -> FraudDetectionResult:
    from app.models.finance import FinanceEntry
    from app.models.note import Note

    today = date.today()
    since = today - timedelta(days=30)
    since_dt = datetime.combine(since, datetime.min.time(), tzinfo=UTC)

    # Scan recent finance entries
    fin_result = await db.execute(
        select(FinanceEntry).where(
            FinanceEntry.organization_id == org_id,
            FinanceEntry.created_at >= since_dt,
        ).limit(500)
    )
    entries = list(fin_result.scalars().all())

    # Scan recent notes
    notes_result = await db.execute(
        select(Note).where(
            Note.organization_id == org_id,
            Note.created_at >= since_dt,
        ).limit(200)
    )
    notes = list(notes_result.scalars().all())

    all_signals: list[dict[str, str | int]] = []

    for entry in entries:
        text = f"{entry.description or ''} {getattr(entry, 'note', '') or ''}"
        for sig in _scan_for_fraud(text):
            sig["source"] = f"finance:{entry.id}"
            all_signals.append(sig)

    for note in notes:
        text = f"{note.title or ''} {note.content or ''}"
        for sig in _scan_for_fraud(text):
            sig["source"] = f"note:{note.id}"
            all_signals.append(sig)

    # Check for duplicate amounts in finance
    amounts = [float(entry.amount) for entry in entries if entry.amount]
    amount_counts = Counter(amounts)
    duplicates = {amt: cnt for amt, cnt in amount_counts.items() if cnt >= 2 and amt > 0}
    for amt, cnt in list(duplicates.items())[:5]:
        all_signals.append({
            "category": "duplicate_transaction",
            "severity": "medium",
            "title": "Duplicate amount detected",
            "description": f"Amount {amt} appears {cnt} times in recent transactions",
            "source": "finance_analysis",
            "risk_score": 55,
        })

    # Deduplicate by category+source
    seen: set[str] = set()
    unique_signals: list[dict[str, str | int]] = []
    for sig in all_signals:
        key = f"{sig['category']}:{sig['source']}"
        if key not in seen:
            seen.add(key)
            unique_signals.append(sig)

    signal_records = [
        FraudSignalOut(
            category=str(sig["category"]),
            severity=str(sig["severity"]),
            title=str(sig["title"]),
            description=str(sig["description"])[:500],
            source=str(sig["source"])[:80],
            risk_score=int(sig.get("risk_score", 50)),
        )
        for sig in unique_signals[:50]
    ]

    risk_breakdown: dict[str, int] = {}
    for sig in signal_records:
        risk_breakdown[sig.category] = risk_breakdown.get(sig.category, 0) + 1

    return FraudDetectionResult(
        scope=scope,
        signals_found=len(signal_records),
        signals=signal_records,
        risk_breakdown=risk_breakdown,
        total_anomalies=len(signal_records),
        message=f"Fraud scan completed. {len(signal_records)} anomaly signal(s) detected.",
    )


async def get_fraud_layer_report(
    db: AsyncSession,
    org_id: int,
) -> FraudLayerReport:
    result = await detect_fraud(db, org_id, scope="layer_report")

    # Active guardrails
    policy_count_result = await db.execute(
        select(sa_func.count(PolicyRule.id)).where(
            PolicyRule.organization_id == org_id,
            PolicyRule.is_active.is_(True),
            PolicyRule.title.like("%Fraud%"),
        )
    )
    guardrails_active = int(policy_count_result.scalar() or 0)

    score = 100
    for sig in result.signals:
        if sig.severity == "critical":
            score -= 25
        elif sig.severity == "high":
            score -= 15
        elif sig.severity == "medium":
            score -= 8
    score += min(guardrails_active * 5, 15)
    score = max(0, min(100, score))

    recommendations: list[str] = []
    if any(s.severity == "critical" for s in result.signals):
        recommendations.append("Critical fraud risk detected. Immediate investigation required.")
    if result.signals_found > 3:
        recommendations.append("Multiple fraud signals found. Run detailed financial audit.")
    if guardrails_active == 0:
        recommendations.append("Create fraud-specific policy rules for automated monitoring.")
    if not result.signals:
        recommendations.append("No fraud signals detected. Maintain regular scanning schedule.")

    return FraudLayerReport(
        fraud_risk_score=score,
        total_anomalies_30d=result.total_anomalies,
        risk_breakdown=result.risk_breakdown,
        top_signals=result.signals[:5],
        guardrails_active=guardrails_active,
        recommendations=recommendations if recommendations else ["Financial integrity looks healthy."],
    )
