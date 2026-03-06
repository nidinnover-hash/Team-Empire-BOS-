"""Control plane endpoints for the dead-letter queue."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_api_user, get_db
from app.core.rbac import require_roles
from app.platform.dead_letter.inspector import (
    count_by_source_type,
    count_by_status,
    get_entry,
    list_entries,
)
from app.platform.dead_letter.reprocessor import archive_entry, resolve_entry, retry_entry
from app.schemas.dead_letter import DeadLetterCountsRead, DeadLetterEntryRead, DeadLetterListRead

router = APIRouter()


@router.get(
    "/dead-letter",
    response_model=DeadLetterListRead,
    dependencies=[Depends(require_roles("CEO", "ADMIN"))],
)
async def list_dead_letter_entries(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_api_user),
    status: str | None = Query(None, description="Filter by status: pending, retrying, resolved, archived"),
    source_type: str | None = Query(None, description="Filter by source: webhook, scheduler, workflow"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> DeadLetterListRead:
    org_id = int(user["org_id"])
    items = await list_entries(
        db, org_id, status=status, source_type=source_type, limit=limit, offset=offset,
    )
    return DeadLetterListRead(
        generated_at=datetime.now(UTC),
        count=len(items),
        items=[DeadLetterEntryRead.model_validate(e) for e in items],
    )


@router.get(
    "/dead-letter/counts",
    response_model=DeadLetterCountsRead,
    dependencies=[Depends(require_roles("CEO", "ADMIN", "MANAGER"))],
)
async def get_dead_letter_counts(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_api_user),
) -> DeadLetterCountsRead:
    org_id = int(user["org_id"])
    by_status = await count_by_status(db, org_id)
    by_source = await count_by_source_type(db, org_id)
    return DeadLetterCountsRead(
        generated_at=datetime.now(UTC),
        by_status=by_status,
        by_source_type=by_source,
        total_pending=by_status.get("pending", 0),
    )


@router.get(
    "/dead-letter/{entry_id}",
    response_model=DeadLetterEntryRead,
    dependencies=[Depends(require_roles("CEO", "ADMIN"))],
)
async def get_dead_letter_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_api_user),
) -> DeadLetterEntryRead:
    from fastapi import HTTPException

    org_id = int(user["org_id"])
    entry = await get_entry(db, entry_id, org_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Dead-letter entry not found")
    return DeadLetterEntryRead.model_validate(entry)


@router.post(
    "/dead-letter/{entry_id}/retry",
    response_model=DeadLetterEntryRead,
    dependencies=[Depends(require_roles("CEO", "ADMIN"))],
)
async def retry_dead_letter_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_api_user),
) -> DeadLetterEntryRead:
    from fastapi import HTTPException

    org_id = int(user["org_id"])
    entry = await retry_entry(db, entry_id, org_id, actor_user_id=int(user["id"]))
    if entry is None:
        raise HTTPException(status_code=404, detail="Dead-letter entry not found")
    return DeadLetterEntryRead.model_validate(entry)


@router.post(
    "/dead-letter/{entry_id}/resolve",
    response_model=DeadLetterEntryRead,
    dependencies=[Depends(require_roles("CEO", "ADMIN"))],
)
async def resolve_dead_letter_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_api_user),
) -> DeadLetterEntryRead:
    from fastapi import HTTPException

    org_id = int(user["org_id"])
    entry = await resolve_entry(db, entry_id, org_id, actor_user_id=int(user["id"]))
    if entry is None:
        raise HTTPException(status_code=404, detail="Dead-letter entry not found")
    return DeadLetterEntryRead.model_validate(entry)


@router.post(
    "/dead-letter/{entry_id}/archive",
    response_model=DeadLetterEntryRead,
    dependencies=[Depends(require_roles("CEO", "ADMIN"))],
)
async def archive_dead_letter_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_api_user),
) -> DeadLetterEntryRead:
    from fastapi import HTTPException

    org_id = int(user["org_id"])
    entry = await archive_entry(db, entry_id, org_id, actor_user_id=int(user["id"]))
    if entry is None:
        raise HTTPException(status_code=404, detail="Dead-letter entry not found")
    return DeadLetterEntryRead.model_validate(entry)
