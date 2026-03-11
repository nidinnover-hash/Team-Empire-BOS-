"""Deal CRUD + pipeline analytics endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.idempotency import build_fingerprint, get_cached_response, store_response
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.deal import DealCreate, DealRead, DealSummary, DealUpdate
from app.services import deal as deal_service

router = APIRouter(prefix="/deals", tags=["Deals"])


@router.post("", response_model=DealRead, status_code=201)
async def create_deal(
    data: DealCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DealRead:
    if idempotency_key:
        scope = f"deal:create:{actor['org_id']}"
        fp = build_fingerprint(data.model_dump())
        cached = get_cached_response(scope, idempotency_key, fingerprint=fp)
        if cached:
            return DealRead.model_validate(cached)
    deal = await deal_service.create_deal(
        db, data.model_dump(), organization_id=actor["org_id"],
        owner_user_id=actor["id"],
    )
    await record_action(
        db, event_type="deal_created", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="deal",
        entity_id=deal.id, payload_json={"title": deal.title, "value": float(deal.value)},
    )
    result = DealRead.model_validate(deal, from_attributes=True)
    if idempotency_key:
        store_response(scope, idempotency_key, result.model_dump(), fingerprint=fp)
    return result


@router.get("", response_model=list[DealRead])
async def list_deals(
    contact_id: int | None = Query(None),
    stage: str | None = Query(None, max_length=30),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[DealRead]:
    deals = await deal_service.list_deals(
        db, organization_id=actor["org_id"],
        contact_id=contact_id, stage=stage, limit=limit, offset=offset,
    )
    return [DealRead.model_validate(d, from_attributes=True) for d in deals]


@router.get("/summary", response_model=DealSummary)
async def deal_summary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DealSummary:
    return DealSummary.model_validate(
        await deal_service.get_deal_summary(db, organization_id=actor["org_id"])
    )


@router.get("/forecast")
async def deal_forecast(
    months: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """Revenue forecast based on pipeline deals, probability, and expected close dates."""
    return await deal_service.get_deal_forecast(db, organization_id=actor["org_id"], months=months)


@router.get("/{deal_id}", response_model=DealRead)
async def get_deal(
    deal_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> DealRead:
    deal = await deal_service.get_deal(db, deal_id, actor["org_id"])
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return DealRead.model_validate(deal, from_attributes=True)


@router.patch("/{deal_id}", response_model=DealRead)
async def update_deal(
    deal_id: int,
    data: DealUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DealRead:
    deal = await deal_service.update_deal(
        db, deal_id, actor["org_id"], **data.model_dump(exclude_unset=True),
    )
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    await record_action(
        db, event_type="deal_updated", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="deal",
        entity_id=deal.id, payload_json={"stage": deal.stage, "value": float(deal.value)},
    )
    return DealRead.model_validate(deal, from_attributes=True)


@router.delete("/{deal_id}", status_code=204)
async def delete_deal(
    deal_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await deal_service.delete_deal(db, deal_id, actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Deal not found")
    await record_action(
        db, event_type="deal_deleted", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="deal",
        entity_id=deal_id, payload_json={},
    )
