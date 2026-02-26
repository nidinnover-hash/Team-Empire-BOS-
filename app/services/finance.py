from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import FinanceEntry
from app.schemas.finance import (
    FinanceEfficiencyFinding,
    FinanceEfficiencyRecommendation,
    FinanceEfficiencyReport,
    FinanceEntryCreate,
    FinanceSummary,
)


async def create_entry(
    db: AsyncSession, data: FinanceEntryCreate, organization_id: int
) -> FinanceEntry:
    entry = FinanceEntry(**data.model_dump(), organization_id=organization_id)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def list_entries(
    db: AsyncSession, organization_id: int, limit: int = 100
) -> list[FinanceEntry]:
    result = await db.execute(
        select(FinanceEntry)
        .where(FinanceEntry.organization_id == organization_id)
        .order_by(FinanceEntry.entry_date.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_summary(db: AsyncSession, organization_id: int) -> FinanceSummary:
    income_result = await db.execute(
        select(func.sum(FinanceEntry.amount)).where(
            FinanceEntry.type == "income",
            FinanceEntry.organization_id == organization_id,
        )
    )
    expense_result = await db.execute(
        select(func.sum(FinanceEntry.amount)).where(
            FinanceEntry.type == "expense",
            FinanceEntry.organization_id == organization_id,
        )
    )
    total_income = Decimal(str(income_result.scalar() or 0))
    total_expense = Decimal(str(expense_result.scalar() or 0))
    return FinanceSummary(
        total_income=float(total_income),
        total_expense=float(total_expense),
        balance=float(total_income - total_expense),
    )


_DIGITAL_CATEGORY_KEYWORDS = {
    "software",
    "saas",
    "subscription",
    "cloud",
    "hosting",
    "ai",
    "ads",
    "marketing",
    "tools",
    "internet",
    "domain",
}
_DIGITAL_DESC_KEYWORDS = {
    "openai",
    "anthropic",
    "groq",
    "meta ads",
    "google ads",
    "aws",
    "gcp",
    "azure",
    "clickup",
    "notion",
    "slack",
    "github",
    "hosting",
    "domain",
    "subscription",
    "saas",
    "software",
}


def _is_digital_entry(entry: FinanceEntry) -> bool:
    category = (entry.category or "").strip().lower()
    description = (entry.description or "").strip().lower()
    if any(k in category for k in _DIGITAL_CATEGORY_KEYWORDS):
        return True
    return any(k in description for k in _DIGITAL_DESC_KEYWORDS)


async def get_expenditure_efficiency(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 30,
) -> FinanceEfficiencyReport:
    end_date = date.today()
    start_date = end_date - timedelta(days=max(window_days - 1, 0))
    result = await db.execute(
        select(FinanceEntry).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.entry_date >= start_date,
            FinanceEntry.entry_date <= end_date,
        ).limit(5000)
    )
    rows = list(result.scalars().all())
    income = sum((Decimal(str(x.amount)) for x in rows if x.type == "income"), Decimal("0"))
    expenses = [x for x in rows if x.type == "expense"]
    total_expense = sum((Decimal(str(x.amount)) for x in expenses), Decimal("0"))
    digital_expenses = [x for x in expenses if _is_digital_entry(x)]
    digital_total = sum((Decimal(str(x.amount)) for x in digital_expenses), Decimal("0"))
    ratio = float(digital_total / income) if income > 0 else (1.0 if digital_total > 0 else 0.0)

    score = 100
    findings: list[FinanceEfficiencyFinding] = []
    recommendations: list[FinanceEfficiencyRecommendation] = []

    if income <= 0 and digital_total > 0:
        score -= 40
        findings.append(
            FinanceEfficiencyFinding(
                code="digital_spend_without_income",
                severity="high",
                message="Digital spend exists in this window, but no income was recorded.",
            )
        )
    elif ratio >= 0.35:
        score -= 35
        findings.append(
            FinanceEfficiencyFinding(
                code="high_digital_spend_ratio",
                severity="high",
                message="Digital spend exceeds 35% of recorded income for the selected window.",
            )
        )
    elif ratio >= 0.20:
        score -= 20
        findings.append(
            FinanceEfficiencyFinding(
                code="elevated_digital_spend_ratio",
                severity="medium",
                message="Digital spend exceeds 20% of recorded income.",
            )
        )
    elif ratio >= 0.10:
        score -= 10
        findings.append(
            FinanceEfficiencyFinding(
                code="watch_digital_spend_ratio",
                severity="low",
                message="Digital spend is above 10% of recorded income. Track ROI by tool/channel.",
            )
        )

    if digital_total > 0:
        max_single = max(Decimal(str(x.amount)) for x in digital_expenses)
        concentration = float(max_single / digital_total)
        if concentration >= 0.45:
            score -= 15
            findings.append(
                FinanceEfficiencyFinding(
                    code="vendor_concentration_risk",
                    severity="medium",
                    message="A single digital cost dominates spend in this window.",
                )
            )

    recurring_like = [
        x for x in digital_expenses
        if "subscription" in (x.category or "").lower()
        or "saas" in (x.category or "").lower()
        or "subscription" in (x.description or "").lower()
        or "monthly" in (x.description or "").lower()
    ]
    if len(recurring_like) >= 5:
        score -= 10
        findings.append(
            FinanceEfficiencyFinding(
                code="subscription_sprawl",
                severity="medium",
                message="Multiple recurring digital charges detected. Review overlaps and inactive seats.",
            )
        )

    score = max(0, min(100, score))
    if ratio >= 0.20:
        potential = float(round(digital_total * Decimal("0.12"), 2))
        recommendations.append(
            FinanceEfficiencyRecommendation(
                title="Run subscription and seat audit",
                action="Cancel inactive tools, reduce unused seats, and consolidate duplicate SaaS tools.",
                estimated_monthly_savings=potential,
            )
        )
    if recurring_like:
        recommendations.append(
            FinanceEfficiencyRecommendation(
                title="Convert monthly tools to annual only after ROI proof",
                action="Keep monthly plans during validation; switch to annual only for proven high-ROI tools.",
                estimated_monthly_savings=float(round(digital_total * Decimal("0.04"), 2)),
            )
        )
    if not recommendations:
        recommendations.append(
            FinanceEfficiencyRecommendation(
                title="Maintain current spend discipline",
                action="Continue tracking digital costs with owner, purpose, and expected business outcome.",
                estimated_monthly_savings=0.0,
            )
        )

    return FinanceEfficiencyReport(
        window_days=window_days,
        income_in_window=float(income),
        total_expense_in_window=float(total_expense),
        digital_expense_in_window=float(digital_total),
        digital_expense_ratio=round(ratio, 4),
        efficiency_score=score,
        findings=findings,
        recommendations=recommendations,
    )
