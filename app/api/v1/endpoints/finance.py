from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.finance import FinanceEntryCreate, FinanceEntryRead, FinanceSummary
from app.services import finance as finance_service

router = APIRouter(prefix="/finance", tags=["Finance"])


@router.get("/summary", response_model=FinanceSummary)
async def get_summary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
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
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[FinanceEntryRead]:
    """List all finance entries, newest date first."""
    return await finance_service.list_entries(db, organization_id=actor["org_id"])
