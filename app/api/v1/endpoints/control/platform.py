"""Platform observability — signals dashboard, decision log, and system counters."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.models.decision_trace import DecisionTrace
from app.models.signal import Signal
from app.schemas.control import (
    DecisionLogRead,
    DecisionTraceItem,
    PlatformCountersRead,
    SignalDashboardRead,
    SignalItem,
)

router = APIRouter()


@router.get("/signals/recent", response_model=SignalDashboardRead)
async def signals_recent(
    topic: str | None = Query(None, max_length=120),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SignalDashboardRead:
    """List recent signals for the organization."""
    org_id = int(actor["org_id"])
    query = (
        select(Signal)
        .where(Signal.organization_id == org_id)
        .order_by(desc(Signal.occurred_at))
        .limit(limit)
    )
    if topic:
        query = query.where(Signal.topic == topic)
    rows = (await db.execute(query)).scalars().all()
    items = [
        SignalItem(
            signal_id=r.signal_id,
            topic=r.topic,
            category=r.category,
            source=r.source,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            occurred_at=r.occurred_at,
            summary_text=r.summary_text,
        )
        for r in rows
    ]
    return SignalDashboardRead(
        generated_at=datetime.now(UTC),
        count=len(items),
        items=items,
    )


@router.get("/decisions/log", response_model=DecisionLogRead)
async def decisions_log(
    trace_type: str | None = Query(None, max_length=64),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DecisionLogRead:
    """List recent decision traces for the organization."""
    org_id = int(actor["org_id"])
    query = (
        select(DecisionTrace)
        .where(DecisionTrace.organization_id == org_id)
        .order_by(desc(DecisionTrace.created_at))
        .limit(limit)
    )
    if trace_type:
        query = query.where(DecisionTrace.trace_type == trace_type)
    rows = (await db.execute(query)).scalars().all()
    items = [
        DecisionTraceItem(
            id=r.id,
            trace_type=r.trace_type,
            title=r.title,
            summary=r.summary,
            confidence_score=r.confidence_score,
            actor_user_id=r.actor_user_id,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return DecisionLogRead(
        generated_at=datetime.now(UTC),
        count=len(items),
        items=items,
    )


@router.get("/platform/counters", response_model=PlatformCountersRead)
async def platform_counters(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> PlatformCountersRead:
    """Aggregate counters for signals, decisions, and signal topic distribution."""
    org_id = int(actor["org_id"])
    now = datetime.now(UTC)
    cutoff_24h = now - timedelta(hours=24)

    signals_24h = (
        await db.execute(
            select(func.count(Signal.id)).where(
                Signal.organization_id == org_id,
                Signal.occurred_at >= cutoff_24h,
            )
        )
    ).scalar_one()
    decisions_24h = (
        await db.execute(
            select(func.count(DecisionTrace.id)).where(
                DecisionTrace.organization_id == org_id,
                DecisionTrace.created_at >= cutoff_24h,
            )
        )
    ).scalar_one()

    # Top topics by volume (last 24h)
    topic_rows = (
        await db.execute(
            select(Signal.topic, func.count(Signal.id).label("cnt"))
            .where(
                Signal.organization_id == org_id,
                Signal.occurred_at >= cutoff_24h,
            )
            .group_by(Signal.topic)
            .order_by(desc("cnt"))
            .limit(20)
        )
    ).all()
    topic_counts = {str(row[0]): int(row[1]) for row in topic_rows}

    # In-process signal counters (since process start)
    from app.platform.signals.consumers import get_signal_counts

    return PlatformCountersRead(
        generated_at=now,
        signals_24h=int(signals_24h or 0),
        decisions_24h=int(decisions_24h or 0),
        topic_counts_24h=topic_counts,
        in_process_signal_counts=get_signal_counts(),
    )
