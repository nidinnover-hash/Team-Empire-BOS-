from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import cast

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.observability import (
    AICallLogRead,
    DecisionTraceSummaryRead,
    ObservabilitySummaryRead,
)
from app.services import observability as obs_service

router = APIRouter(prefix="/observability", tags=["Observability"])


@router.get("/summary", response_model=ObservabilitySummaryRead)
async def observability_summary(
    days: int = Query(default=7, ge=1, le=90),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> ObservabilitySummaryRead:
    payload = await obs_service.get_observability_summary(db, org_id=actor["org_id"], days=days)
    return cast(ObservabilitySummaryRead, ObservabilitySummaryRead.model_validate(payload))


@router.get("/ai-calls", response_model=list[AICallLogRead])
async def recent_ai_calls(
    limit: int = Query(default=50, ge=1, le=200),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[AICallLogRead]:
    payload = await obs_service.get_recent_ai_calls(db, org_id=actor["org_id"], limit=limit)
    return [AICallLogRead.model_validate(item) for item in payload]


@router.get("/decision-traces", response_model=list[DecisionTraceSummaryRead])
async def recent_decisions(
    limit: int = Query(default=20, ge=1, le=100),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[DecisionTraceSummaryRead]:
    payload = await obs_service.get_recent_decisions(db, org_id=actor["org_id"], limit=limit)
    return [DecisionTraceSummaryRead.model_validate(item) for item in payload]
