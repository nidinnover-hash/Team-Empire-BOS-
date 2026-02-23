from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.execution import ExecutionRead
from app.services import execution as execution_service

router = APIRouter(prefix="/executions", tags=["Executions"])


@router.get("", response_model=list[ExecutionRead])
async def list_executions(
    status: Literal["running", "succeeded", "failed", "skipped"] | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[ExecutionRead]:
    return await execution_service.list_executions(
        db,
        organization_id=actor["org_id"],
        status=status,
    )
