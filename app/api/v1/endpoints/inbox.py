from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.inbox import UnifiedInboxItem
from app.services import inbox as inbox_service

router = APIRouter(prefix="/inbox", tags=["Inbox"])


@router.get("/unified", response_model=list[UnifiedInboxItem])
async def unified_inbox(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[UnifiedInboxItem]:
    return await inbox_service.get_unified_inbox(
        db=db,
        org_id=actor["org_id"],
        limit=limit,
        offset=offset,
    )
