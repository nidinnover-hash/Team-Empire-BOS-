"""Service for workspace-level Decision Cards."""
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.decision_card import DecisionCard
from app.schemas.decision_card import DecisionCardCreate, DecisionCardDecide

logger = logging.getLogger(__name__)


async def list_decision_cards(
    db: AsyncSession,
    org_id: int,
    *,
    workspace_id: int | None = None,
    status: str | None = None,
    urgency: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[DecisionCard]:
    query = (
        select(DecisionCard)
        .where(DecisionCard.organization_id == org_id)
        .order_by(DecisionCard.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    if workspace_id is not None:
        query = query.where(DecisionCard.workspace_id == workspace_id)
    if status:
        query = query.where(DecisionCard.status == status)
    if urgency:
        query = query.where(DecisionCard.urgency == urgency)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_decision_card(
    db: AsyncSession, org_id: int, card_id: int,
) -> DecisionCard | None:
    result = await db.execute(
        select(DecisionCard).where(
            DecisionCard.id == card_id,
            DecisionCard.organization_id == org_id,
        )
    )
    return result.scalar_one_or_none()


async def create_decision_card(
    db: AsyncSession,
    org_id: int,
    data: DecisionCardCreate,
    proposed_by: int | None = None,
) -> DecisionCard:
    """Create a new decision card (typically proposed by AI or automation)."""
    options_json = json.dumps([opt.model_dump() for opt in data.options])
    card = DecisionCard(
        organization_id=org_id,
        workspace_id=data.workspace_id,
        title=data.title,
        context_summary=data.context_summary,
        options_json=options_json,
        recommendation=data.recommendation,
        category=data.category,
        urgency=data.urgency,
        status="pending",
        proposed_by=proposed_by,
        source_type=data.source_type,
        source_id=data.source_id,
        expires_at=data.expires_at,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return card


async def decide_card(
    db: AsyncSession,
    org_id: int,
    card_id: int,
    decision: DecisionCardDecide,
    decided_by: int,
) -> DecisionCard | None:
    """Record a human decision on a pending card."""
    card = await get_decision_card(db, org_id, card_id)
    if not card or card.status != "pending":
        return None
    card.status = "decided"
    card.chosen_option = decision.chosen_option
    card.decision_rationale = decision.decision_rationale
    card.decided_by = decided_by
    card.decided_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(card)
    return card


async def defer_card(
    db: AsyncSession,
    org_id: int,
    card_id: int,
    rationale: str | None,
    decided_by: int,
) -> DecisionCard | None:
    """Defer a pending decision for later."""
    card = await get_decision_card(db, org_id, card_id)
    if not card or card.status != "pending":
        return None
    card.status = "deferred"
    card.decision_rationale = rationale
    card.decided_by = decided_by
    card.decided_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(card)
    return card


async def get_pending_count(
    db: AsyncSession, org_id: int, *, workspace_id: int | None = None,
) -> int:
    """Count pending decision cards."""
    from sqlalchemy import func
    query = select(func.count(DecisionCard.id)).where(
        DecisionCard.organization_id == org_id,
        DecisionCard.status == "pending",
    )
    if workspace_id is not None:
        query = query.where(DecisionCard.workspace_id == workspace_id)
    result = await db.execute(query)
    return result.scalar() or 0
