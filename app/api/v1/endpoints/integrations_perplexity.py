from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.integration import (
    PerplexityConnectRequest,
    PerplexitySearchRequest,
    PerplexitySearchResult,
    PerplexityStatusRead,
)
from app.services import perplexity_service

router = APIRouter(tags=["Integrations"])


@router.post("/perplexity/connect", response_model=PerplexityStatusRead, status_code=201)
async def perplexity_connect(
    data: PerplexityConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> PerplexityStatusRead:
    try:
        info = await perplexity_service.connect_perplexity(
            db, org_id=int(actor["org_id"]), api_key=data.api_key,
        )
    except (RuntimeError, ValueError, TypeError, TimeoutError, ConnectionError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"Perplexity connection failed: {type(exc).__name__}") from exc
    await record_action(
        db, event_type="integration_connected", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="integration",
        entity_id=info["id"], payload_json={"type": "perplexity", "status": "ok"},
    )
    return PerplexityStatusRead(connected=True)


@router.get("/perplexity/status", response_model=PerplexityStatusRead)
async def perplexity_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> PerplexityStatusRead:
    status = await perplexity_service.get_perplexity_status(db, org_id=int(actor["org_id"]))
    return PerplexityStatusRead(**status)


@router.post("/perplexity/search", response_model=PerplexitySearchResult)
async def perplexity_search(
    data: PerplexitySearchRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> PerplexitySearchResult:
    try:
        result = await perplexity_service.search_web(
            db, org_id=int(actor["org_id"]), query=data.query, max_tokens=data.max_tokens,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PerplexitySearchResult(content=result["content"], citations=result["citations"])
