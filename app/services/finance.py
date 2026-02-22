from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import FinanceEntry
from app.schemas.finance import FinanceEntryCreate, FinanceSummary


async def create_entry(
    db: AsyncSession, data: FinanceEntryCreate, organization_id: int = 1
) -> FinanceEntry:
    entry = FinanceEntry(**data.model_dump(), organization_id=organization_id)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def list_entries(
    db: AsyncSession, limit: int = 100, organization_id: int = 1
) -> list[FinanceEntry]:
    result = await db.execute(
        select(FinanceEntry)
        .where(FinanceEntry.organization_id == organization_id)
        .order_by(FinanceEntry.entry_date.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_summary(db: AsyncSession, organization_id: int = 1) -> FinanceSummary:
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
    total_income = float(income_result.scalar() or 0)
    total_expense = float(expense_result.scalar() or 0)
    return FinanceSummary(
        total_income=total_income,
        total_expense=total_expense,
        balance=total_income - total_expense,
    )
