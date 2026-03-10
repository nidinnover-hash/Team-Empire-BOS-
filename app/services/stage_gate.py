"""Pipeline stage gate requirements service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stage_gate import StageGate, StageGateOverride


async def create_gate(
    db: AsyncSession, *, organization_id: int, stage: str,
    requirement_type: str = "field", field_name: str | None = None,
    description: str = "", is_blocking: bool = True,
    is_active: bool = True,
) -> StageGate:
    row = StageGate(
        organization_id=organization_id, stage=stage,
        requirement_type=requirement_type, field_name=field_name,
        description=description, is_blocking=is_blocking,
        is_active=is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_gates(
    db: AsyncSession, organization_id: int, *,
    stage: str | None = None, is_active: bool | None = None,
) -> list[StageGate]:
    q = select(StageGate).where(StageGate.organization_id == organization_id)
    if stage:
        q = q.where(StageGate.stage == stage)
    if is_active is not None:
        q = q.where(StageGate.is_active == is_active)
    q = q.order_by(StageGate.stage, StageGate.id)
    return list((await db.execute(q)).scalars().all())


async def get_gate(db: AsyncSession, gate_id: int, organization_id: int) -> StageGate | None:
    q = select(StageGate).where(StageGate.id == gate_id, StageGate.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_gate(db: AsyncSession, gate_id: int, organization_id: int, **kwargs) -> StageGate | None:
    row = await get_gate(db, gate_id, organization_id)
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_gate(db: AsyncSession, gate_id: int, organization_id: int) -> bool:
    row = await get_gate(db, gate_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def record_override(
    db: AsyncSession, *, organization_id: int, gate_id: int,
    deal_id: int, overridden_by_user_id: int, reason: str | None = None,
) -> StageGateOverride:
    row = StageGateOverride(
        organization_id=organization_id, gate_id=gate_id,
        deal_id=deal_id, overridden_by_user_id=overridden_by_user_id,
        reason=reason,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_overrides(
    db: AsyncSession, organization_id: int, *,
    deal_id: int | None = None, gate_id: int | None = None,
) -> list[StageGateOverride]:
    q = select(StageGateOverride).where(StageGateOverride.organization_id == organization_id)
    if deal_id is not None:
        q = q.where(StageGateOverride.deal_id == deal_id)
    if gate_id is not None:
        q = q.where(StageGateOverride.gate_id == gate_id)
    q = q.order_by(StageGateOverride.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def validate_stage(db: AsyncSession, organization_id: int, stage: str, deal_data: dict) -> dict:
    gates = await list_gates(db, organization_id, stage=stage, is_active=True)
    passed = []
    failed = []
    for gate in gates:
        if gate.requirement_type == "field" and gate.field_name:
            if deal_data.get(gate.field_name):
                passed.append({"gate_id": gate.id, "description": gate.description})
            else:
                failed.append({"gate_id": gate.id, "description": gate.description, "blocking": gate.is_blocking})
        else:
            passed.append({"gate_id": gate.id, "description": gate.description})
    can_proceed = all(not f["blocking"] for f in failed)
    return {"stage": stage, "passed": passed, "failed": failed, "can_proceed": can_proceed}
