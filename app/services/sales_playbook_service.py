"""Sales playbook and step service — CRM module.

All business logic for playbooks and steps. Organization-scoped; emits signals for audit.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sales_playbook import Playbook, PlaybookStep
from app.platform.signals import (
    PLAYBOOK_CREATED,
    PLAYBOOK_STEP_EXECUTED,
    PLAYBOOK_UPDATED,
    SignalCategory,
    SignalEnvelope,
    publish_signal,
)
from app.schemas.sales_playbook import (
    PlaybookCreate,
    PlaybookStepCreate,
    PlaybookStepUpdate,
    PlaybookUpdate,
)

logger = logging.getLogger(__name__)

_PROTECTED_PLAYBOOK_FIELDS = frozenset({"id", "organization_id", "created_at"})
_PLAYBOOK_UPDATE_FIELDS = frozenset({"name", "deal_stage", "description", "is_active", "updated_at"})
_PROTECTED_STEP_FIELDS = frozenset({"id", "organization_id", "playbook_id", "created_at"})
_STEP_UPDATE_FIELDS = frozenset({"step_order", "title", "content", "is_required"})


async def _emit_playbook_signal(
    db: AsyncSession | None,
    topic: str,
    organization_id: int,
    playbook: Playbook,
    *,
    actor_user_id: int | None = None,
    entity_id: str | None = None,
    payload_extra: dict | None = None,
) -> None:
    try:
        payload = {"playbook_id": playbook.id, "name": playbook.name}
        if payload_extra:
            payload.update(payload_extra)
        await publish_signal(
            SignalEnvelope(
                topic=topic,
                category=SignalCategory.DOMAIN,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                source="sales_playbook.service",
                entity_type="playbook",
                entity_id=entity_id or str(playbook.id),
                payload=payload,
            ),
            db=db,
        )
    except Exception:
        logger.debug("Signal emission failed for %s playbook_id=%s", topic, playbook.id, exc_info=True)


async def get_playbook(
    db: AsyncSession,
    playbook_id: int,
    organization_id: int,
) -> Playbook | None:
    result = await db.execute(
        select(Playbook).where(
            Playbook.id == playbook_id,
            Playbook.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def list_playbooks(
    db: AsyncSession,
    organization_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
    is_active: bool | None = None,
    deal_stage: str | None = None,
) -> list[Playbook]:
    query = select(Playbook).where(Playbook.organization_id == organization_id)
    if is_active is not None:
        query = query.where(Playbook.is_active.is_(is_active))
    if deal_stage is not None:
        query = query.where(Playbook.deal_stage == deal_stage)
    query = query.order_by(Playbook.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_playbook(
    db: AsyncSession,
    data: PlaybookCreate,
    organization_id: int,
) -> Playbook:
    payload = data.model_dump(exclude={"steps"})
    playbook = Playbook(organization_id=organization_id, **payload)
    db.add(playbook)
    await db.flush()
    for step_data in data.steps:
        step = PlaybookStep(
            organization_id=organization_id,
            playbook_id=playbook.id,
            step_order=step_data.step_order,
            title=step_data.title,
            content=step_data.content,
            is_required=step_data.is_required,
        )
        db.add(step)
    await db.commit()
    await db.refresh(playbook)
    await _emit_playbook_signal(db, PLAYBOOK_CREATED, organization_id, playbook)
    logger.info("playbook created id=%d org=%d", playbook.id, organization_id)
    return playbook


async def update_playbook(
    db: AsyncSession,
    playbook_id: int,
    data: PlaybookUpdate,
    organization_id: int,
    *,
    actor_user_id: int | None = None,
) -> Playbook | None:
    playbook = await get_playbook(db, playbook_id, organization_id)
    if playbook is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key not in _PROTECTED_PLAYBOOK_FIELDS and key in _PLAYBOOK_UPDATE_FIELDS:
            setattr(playbook, key, value)
    await db.commit()
    await db.refresh(playbook)
    await _emit_playbook_signal(db, PLAYBOOK_UPDATED, organization_id, playbook, actor_user_id=actor_user_id)
    logger.info("playbook updated id=%d org=%d", playbook_id, organization_id)
    return playbook


async def get_step(
    db: AsyncSession,
    step_id: int,
    organization_id: int,
    *,
    playbook_id: int | None = None,
) -> PlaybookStep | None:
    query = select(PlaybookStep).where(
        PlaybookStep.id == step_id,
        PlaybookStep.organization_id == organization_id,
    )
    if playbook_id is not None:
        query = query.where(PlaybookStep.playbook_id == playbook_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_steps(
    db: AsyncSession,
    playbook_id: int,
    organization_id: int,
) -> list[PlaybookStep]:
    playbook = await get_playbook(db, playbook_id, organization_id)
    if playbook is None:
        return []
    result = await db.execute(
        select(PlaybookStep)
        .where(
            PlaybookStep.playbook_id == playbook_id,
            PlaybookStep.organization_id == organization_id,
        )
        .order_by(PlaybookStep.step_order, PlaybookStep.id)
    )
    return list(result.scalars().all())


async def add_step(
    db: AsyncSession,
    playbook_id: int,
    data: PlaybookStepCreate,
    organization_id: int,
) -> PlaybookStep | None:
    playbook = await get_playbook(db, playbook_id, organization_id)
    if playbook is None:
        return None
    step = PlaybookStep(
        organization_id=organization_id,
        playbook_id=playbook_id,
        step_order=data.step_order,
        title=data.title,
        content=data.content,
        is_required=data.is_required,
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def update_step(
    db: AsyncSession,
    playbook_id: int,
    step_id: int,
    data: PlaybookStepUpdate,
    organization_id: int,
) -> PlaybookStep | None:
    step = await get_step(db, step_id, organization_id, playbook_id=playbook_id)
    if step is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key not in _PROTECTED_STEP_FIELDS and key in _STEP_UPDATE_FIELDS:
            setattr(step, key, value)
    await db.commit()
    await db.refresh(step)
    return step


async def remove_step(
    db: AsyncSession,
    playbook_id: int,
    step_id: int,
    organization_id: int,
) -> bool:
    step = await get_step(db, step_id, organization_id, playbook_id=playbook_id)
    if step is None:
        return False
    await db.delete(step)
    await db.commit()
    return True


async def record_step_execution(
    db: AsyncSession,
    playbook_id: int,
    step_id: int,
    organization_id: int,
    *,
    actor_user_id: int | None = None,
    idempotency_key: str | None = None,
) -> PlaybookStep | None:
    """Record that a playbook step was executed (idempotent when idempotency_key is reused)."""
    playbook = await get_playbook(db, playbook_id, organization_id)
    if playbook is None:
        return None
    step = await get_step(db, step_id, organization_id, playbook_id=playbook_id)
    if step is None:
        return None
    await _emit_playbook_signal(
        db,
        PLAYBOOK_STEP_EXECUTED,
        organization_id,
        playbook,
        entity_id=str(step_id),
        payload_extra={
            "step_id": step_id,
            "step_title": step.title,
            "idempotency_key": idempotency_key,
        },
        actor_user_id=actor_user_id,
    )
    logger.info("playbook step executed playbook_id=%d step_id=%d org=%d", playbook_id, step_id, organization_id)
    return step
