import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import FinanceEntry
from app.schemas.finance import (
    BudgetRead,
    CategoryBreakdown,
    FinanceEfficiencyFinding,
    FinanceEfficiencyRecommendation,
    FinanceEfficiencyReport,
    FinanceEntryCreate,
    FinanceSummary,
    FinanceTrend,
    MonthlyBreakdown,
)

logger = logging.getLogger(__name__)


async def create_entry(
    db: AsyncSession, data: FinanceEntryCreate, organization_id: int
) -> FinanceEntry:
    entry = FinanceEntry(**data.model_dump(), organization_id=organization_id)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    try:
        from app.platform.signals import (
            FINANCE_EXPENSE_RECORDED,
            FINANCE_INVOICE_CREATED,
            SignalCategory,
            SignalEnvelope,
            publish_signal,
        )

        topic = FINANCE_INVOICE_CREATED if entry.entry_type == "income" else FINANCE_EXPENSE_RECORDED
        await publish_signal(
            SignalEnvelope(
                topic=topic,
                category=SignalCategory.DOMAIN,
                organization_id=organization_id,
                source="finance.service",
                entity_type="finance_entry",
                entity_id=str(entry.id),
                payload={"entry_id": entry.id, "entry_type": entry.entry_type, "amount": str(entry.amount)},
            ),
            db=db,
        )
    except Exception:
        logger.debug("Signal emission failed for finance entry %s", entry.id, exc_info=True)
    return entry


async def list_entries(
    db: AsyncSession, organization_id: int, limit: int = 100, offset: int = 0
) -> list[FinanceEntry]:
    result = await db.execute(
        select(FinanceEntry)
        .where(FinanceEntry.organization_id == organization_id)
        .order_by(FinanceEntry.entry_date.desc())
        .offset(offset)
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
    _EFFICIENCY_LIMIT = 5000
    rows = list(result.scalars().all())
    if len(rows) >= _EFFICIENCY_LIMIT:
        logger.warning(
            "Finance efficiency query hit %d-row limit for org=%d window=%d days — results may be truncated",
            _EFFICIENCY_LIMIT, organization_id, window_days,
        )
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


# ── Monthly Trends ───────────────────────────────────────────────────────────

async def get_monthly_trends(
    db: AsyncSession,
    organization_id: int,
    months: int = 6,
) -> FinanceTrend:
    """Month-over-month income/expense breakdown with category analysis."""
    end = date.today()
    start = end.replace(day=1) - timedelta(days=(months - 1) * 30)
    start = start.replace(day=1)

    result = await db.execute(
        select(FinanceEntry).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.entry_date >= start,
            FinanceEntry.entry_date <= end,
        ).order_by(FinanceEntry.entry_date).limit(5000)
    )
    entries = list(result.scalars().all())

    # Group by month
    month_data: dict[str, dict[str, Decimal]] = {}
    cat_data: dict[str, dict[str, Decimal | int]] = {}

    for e in entries:
        key = e.entry_date.strftime("%Y-%m") if hasattr(e.entry_date, "strftime") else str(e.entry_date)[:7]
        if key not in month_data:
            month_data[key] = {"income": Decimal("0"), "expense": Decimal("0")}
        amount = Decimal(str(e.amount))
        if e.type == "income":
            month_data[key]["income"] += amount
        else:
            month_data[key]["expense"] += amount

        # Category breakdown (expenses only)
        if e.type == "expense":
            cat = e.category or "other"
            if cat not in cat_data:
                cat_data[cat] = {"total": Decimal("0"), "count": 0}
            cat_data[cat]["total"] += amount
            cat_data[cat]["count"] += 1

    monthly = []
    for key in sorted(month_data.keys()):
        d = month_data[key]
        monthly.append(MonthlyBreakdown(
            month=key,
            income=float(d["income"]),
            expense=float(d["expense"]),
            net=float(d["income"] - d["expense"]),
        ))

    # Category breakdown with percentages
    total_expense = sum(v["total"] for v in cat_data.values()) or Decimal("1")
    categories = sorted(
        [
            CategoryBreakdown(
                category=cat,
                total=float(v["total"]),
                count=int(v["count"]),
                pct_of_total=round(float(v["total"] / total_expense) * 100, 1),
            )
            for cat, v in cat_data.items()
        ],
        key=lambda x: x.total,
        reverse=True,
    )

    # Trend direction (compare last 2 months)
    def _trend(values: list[float]) -> str:
        if len(values) < 2:
            return "flat"
        diff = values[-1] - values[-2]
        if diff > values[-2] * 0.05:
            return "up"
        if diff < -values[-2] * 0.05:
            return "down"
        return "flat"

    incomes = [m.income for m in monthly]
    expenses = [m.expense for m in monthly]

    return FinanceTrend(
        months=monthly,
        category_breakdown=categories[:15],
        avg_monthly_income=round(sum(incomes) / max(len(incomes), 1), 2),
        avg_monthly_expense=round(sum(expenses) / max(len(expenses), 1), 2),
        income_trend=_trend(incomes),
        expense_trend=_trend(expenses),
    )


# ── Budget Tracking ──────────────────────────────────────────────────────────
# Budgets are stored in profile memory as "budget.<category>" keys.

async def get_budgets(
    db: AsyncSession, organization_id: int,
) -> list[BudgetRead]:
    """Get all budget limits with current month spend comparison."""
    from app.models.memory import ProfileMemory

    # Fetch budget entries from profile memory
    budget_result = await db.execute(
        select(ProfileMemory).where(
            ProfileMemory.organization_id == organization_id,
            ProfileMemory.key.like("budget.%"),
        )
    )
    budget_entries = list(budget_result.scalars().all())

    if not budget_entries:
        return []

    # Get current month spending by category
    today = date.today()
    month_start = today.replace(day=1)
    spend_result = await db.execute(
        select(
            FinanceEntry.category,
            func.sum(FinanceEntry.amount),
        ).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.type == "expense",
            FinanceEntry.entry_date >= month_start,
            FinanceEntry.entry_date <= today,
        ).group_by(FinanceEntry.category)
    )
    spend_by_cat = {row[0]: float(row[1] or 0) for row in spend_result.all()}

    budgets = []
    for entry in budget_entries:
        cat = entry.key.replace("budget.", "")
        try:
            parts = (entry.value or "").split("|", 1)
            limit_val = float(parts[0])
            desc = parts[1] if len(parts) > 1 else None
        except (ValueError, IndexError):
            continue
        spent = spend_by_cat.get(cat, 0.0)
        budgets.append(BudgetRead(
            category=cat,
            monthly_limit=limit_val,
            description=desc,
            spent_this_month=round(spent, 2),
            remaining=round(max(limit_val - spent, 0), 2),
            pct_used=round((spent / limit_val) * 100, 1) if limit_val > 0 else 0.0,
        ))

    return sorted(budgets, key=lambda b: b.pct_used, reverse=True)


async def set_budget(
    db: AsyncSession, organization_id: int,
    category: str, monthly_limit: float, description: str | None = None,
) -> BudgetRead:
    """Set or update a monthly budget for a category."""
    from app.services.memory import upsert_profile_memory

    value = f"{monthly_limit}"
    if description:
        value += f"|{description}"

    await upsert_profile_memory(
        db, organization_id, key=f"budget.{category}", value=value, category="finance",
    )

    # Get current month spend
    today = date.today()
    month_start = today.replace(day=1)
    spend_result = await db.execute(
        select(func.sum(FinanceEntry.amount)).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.type == "expense",
            FinanceEntry.category == category,
            FinanceEntry.entry_date >= month_start,
            FinanceEntry.entry_date <= today,
        )
    )
    spent = float(spend_result.scalar() or 0)

    return BudgetRead(
        category=category,
        monthly_limit=monthly_limit,
        description=description,
        spent_this_month=round(spent, 2),
        remaining=round(max(monthly_limit - spent, 0), 2),
        pct_used=round((spent / monthly_limit) * 100, 1) if monthly_limit > 0 else 0.0,
    )
