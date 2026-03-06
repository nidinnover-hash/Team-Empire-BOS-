from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.models.event import Event
from app.schemas.observability import (
    AICallLogRead,
    AiReliabilityRead,
    DecisionSummaryRead,
    DecisionTimelineItemRead,
    DecisionTraceSummaryRead,
    EventRead,
    ObservabilitySummaryRead,
    SchedulerHealthRead,
    SignalRead,
    StorageSummaryRead,
    WebhookReliabilityRead,
)
from app.services import observability as obs_service

router = APIRouter(prefix="/observability", tags=["Observability"])


@router.get("/summary", response_model=ObservabilitySummaryRead)
async def observability_summary(
    days: int = Query(default=7, ge=1, le=90),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> ObservabilitySummaryRead:
    payload = await obs_service.get_observability_summary(db, org_id=int(actor["org_id"]), days=days)
    return ObservabilitySummaryRead.model_validate(payload)


@router.get("/ai-calls", response_model=list[AICallLogRead])
async def recent_ai_calls(
    limit: int = Query(default=50, ge=1, le=200),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[AICallLogRead]:
    payload = await obs_service.get_recent_ai_calls(db, org_id=int(actor["org_id"]), limit=limit)
    return [AICallLogRead.model_validate(item) for item in payload]


@router.get("/ai-reliability", response_model=AiReliabilityRead)
async def ai_reliability(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=200, ge=1, le=1000),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> AiReliabilityRead:
    payload = await obs_service.get_ai_reliability(
        db,
        org_id=int(actor["org_id"]),
        days=days,
        limit=limit,
    )
    return AiReliabilityRead.model_validate(payload)


@router.get("/scheduler-health", response_model=SchedulerHealthRead)
async def scheduler_health(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=300, ge=1, le=1000),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> SchedulerHealthRead:
    payload = await obs_service.get_scheduler_health(
        db,
        org_id=int(actor["org_id"]),
        days=days,
        limit=limit,
    )
    return SchedulerHealthRead.model_validate(payload)


@router.get("/webhook-reliability", response_model=WebhookReliabilityRead)
async def webhook_reliability(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=300, ge=1, le=1000),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> WebhookReliabilityRead:
    payload = await obs_service.get_webhook_reliability(
        db,
        org_id=int(actor["org_id"]),
        days=days,
        limit=limit,
    )
    return WebhookReliabilityRead.model_validate(payload)


@router.get("/decision-traces", response_model=list[DecisionTraceSummaryRead])
async def recent_decisions(
    limit: int = Query(default=20, ge=1, le=100),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[DecisionTraceSummaryRead]:
    payload = await obs_service.get_recent_decisions(db, org_id=int(actor["org_id"]), limit=limit)
    return [DecisionTraceSummaryRead.model_validate(item) for item in payload]


@router.get("/decision-timeline", response_model=list[DecisionTimelineItemRead])
async def decision_timeline(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=200),
    correlation_id: str | None = Query(default=None, max_length=255),
    approval_id: int | None = Query(default=None, ge=1),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[DecisionTimelineItemRead]:
    payload = await obs_service.get_decision_timeline(
        db,
        org_id=int(actor["org_id"]),
        days=days,
        limit=limit,
        correlation_id=correlation_id,
        approval_id=approval_id,
    )
    return [DecisionTimelineItemRead.model_validate(item) for item in payload]


@router.get("/decision-summary", response_model=DecisionSummaryRead)
async def decision_summary(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=200, ge=1, le=500),
    correlation_id: str | None = Query(default=None, max_length=255),
    approval_id: int | None = Query(default=None, ge=1),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> DecisionSummaryRead:
    payload = await obs_service.get_decision_summary(
        db,
        org_id=int(actor["org_id"]),
        days=days,
        limit=limit,
        correlation_id=correlation_id,
        approval_id=approval_id,
    )
    return DecisionSummaryRead.model_validate(payload)


@router.get("/storage", response_model=StorageSummaryRead)
async def storage_summary(
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> StorageSummaryRead:
    payload = await obs_service.get_storage_summary(db, org_id=int(actor["org_id"]))
    return StorageSummaryRead.model_validate(payload)


@router.get("/signals", response_model=list[SignalRead])
async def list_observability_signals(
    topic: str | None = Query(default=None, max_length=120),
    correlation_id: str | None = Query(default=None, max_length=255),
    entity_type: str | None = Query(default=None, max_length=120),
    entity_id: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=100, ge=1, le=500),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[SignalRead]:
    payload = await obs_service.get_recent_signals(
        db,
        org_id=int(actor["org_id"]),
        limit=limit,
        topic=topic,
        correlation_id=correlation_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    return [SignalRead.model_validate(item) for item in payload]


@router.get("/events", response_model=list[EventRead])
async def list_observability_events(
    event_type: str | None = Query(default=None, max_length=100),
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=100, ge=1, le=500),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[EventRead]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    query = (
        select(Event)
        .where(
            Event.organization_id == int(actor["org_id"]),
            Event.created_at >= cutoff,
        )
        .order_by(Event.created_at.desc())
        .limit(limit)
    )
    if event_type:
        query = query.where(Event.event_type == event_type)
    rows = (await db.execute(query)).scalars().all()
    return [
        EventRead(
            id=row.id,
            organization_id=row.organization_id,
            event_type=row.event_type,
            actor_user_id=row.actor_user_id,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            payload=row.payload_json or {},
            created_at=row.created_at,
        )
        for row in rows
    ]
