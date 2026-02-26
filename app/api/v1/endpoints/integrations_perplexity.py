import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints._integration_helpers import (
    CONNECT_EXCEPTIONS,
    audit_connect_success,
    handle_connect_error,
)
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.integration import (
    PerplexityConnectRequest,
    PerplexitySearchRequest,
    PerplexitySearchResult,
    PerplexityStatusRead,
)
from app.services import perplexity_service

logger = logging.getLogger(__name__)

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
    except CONNECT_EXCEPTIONS as exc:
        await handle_connect_error(db, integration_type="perplexity", actor=actor, exc=exc)
    await audit_connect_success(db, integration_type="perplexity", actor=actor, entity_id=info["id"])
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
        logger.warning("perplexity search failed: %s", exc)
        raise HTTPException(status_code=400, detail="Search failed. Check connection and try again.") from exc
    return PerplexitySearchResult(content=result["content"], citations=result["citations"])
