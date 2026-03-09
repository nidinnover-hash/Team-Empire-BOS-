from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles, require_sensitive_financial_roles
from app.schemas.finance import (
    BudgetCreate,
    BudgetRead,
    FinanceEfficiencyReport,
    FinanceEntryCreate,
    FinanceEntryRead,
    FinanceSummary,
    FinanceTrend,
)
from app.services import finance as finance_service

router = APIRouter(prefix="/finance", tags=["Finance"])


@router.get("/summary", response_model=FinanceSummary)
async def get_summary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_sensitive_financial_roles()),
) -> FinanceSummary:
    """Total income, expenses, and current balance."""
    return await finance_service.get_summary(db, organization_id=actor["org_id"])


@router.post("", response_model=FinanceEntryRead, status_code=201)
async def create_entry(
    data: FinanceEntryCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> FinanceEntryRead:
    """Log an income or expense entry."""
    return await finance_service.create_entry(db, data, organization_id=actor["org_id"])


@router.get("", response_model=list[FinanceEntryRead])
async def list_entries(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_sensitive_financial_roles()),
) -> list[FinanceEntryRead]:
    """List all finance entries, newest date first."""
    from app.core.data_classification import sanitize_list_for_role

    entries = await finance_service.list_entries(db, organization_id=actor["org_id"], limit=limit, offset=offset)
    raw = [FinanceEntryRead.model_validate(e, from_attributes=True).model_dump() for e in entries]
    sanitized = sanitize_list_for_role(raw, "finance_entries", str(actor.get("role", "STAFF")))
    return [FinanceEntryRead.model_validate(d) for d in sanitized]


@router.get("/trends", response_model=FinanceTrend)
async def get_trends(
    months: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_sensitive_financial_roles()),
) -> FinanceTrend:
    """Month-over-month income/expense trends with category breakdown."""
    return await finance_service.get_monthly_trends(db, organization_id=actor["org_id"], months=months)


@router.get("/budgets", response_model=list[BudgetRead])
async def list_budgets(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_sensitive_financial_roles()),
) -> list[BudgetRead]:
    """List all category budgets with current month spend comparison."""
    return await finance_service.get_budgets(db, organization_id=actor["org_id"])


@router.post("/budgets", response_model=BudgetRead, status_code=201)
async def set_budget(
    data: BudgetCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> BudgetRead:
    """Set or update a monthly budget limit for a category."""
    return await finance_service.set_budget(
        db, organization_id=actor["org_id"],
        category=data.category, monthly_limit=data.monthly_limit, description=data.description,
    )


@router.get("/efficiency", response_model=FinanceEfficiencyReport)
async def get_expenditure_efficiency(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_sensitive_financial_roles()),
) -> FinanceEfficiencyReport:
    """
    Digital expenditure efficiency report for the selected rolling window.
    Scores spend quality, flags risk, and recommends savings actions.
    """
    return await finance_service.get_expenditure_efficiency(
        db=db,
        organization_id=actor["org_id"],
        window_days=window_days,
    )
