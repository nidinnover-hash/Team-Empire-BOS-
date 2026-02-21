from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import FinanceEntry
from app.schemas.finance import FinanceEntryCreate, FinanceSummary


async def create_entry(db: AsyncSession, data: FinanceEntryCreate) -> FinanceEntry:
    entry = FinanceEntry(**data.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def list_entries(db: AsyncSession, limit: int = 100) -> list[FinanceEntry]:
    result = await db.execute(
        select(FinanceEntry).order_by(FinanceEntry.entry_date.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_summary(db: AsyncSession) -> FinanceSummary:
    income_result = await db.execute(
        select(func.sum(FinanceEntry.amount)).where(FinanceEntry.type == "income")
    )
    expense_result = await db.execute(
        select(func.sum(FinanceEntry.amount)).where(FinanceEntry.type == "expense")
    )
    total_income = float(income_result.scalar() or 0)
    total_expense = float(expense_result.scalar() or 0)
    return FinanceSummary(
        total_income=total_income,
        total_expense=total_expense,
        balance=total_income - total_expense,
    )
