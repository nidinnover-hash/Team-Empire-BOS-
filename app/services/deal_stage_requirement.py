"""Deal stage requirement service — manage requirements and check compliance."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal_stage_requirement import DealRequirementCheck, DealStageRequirement


async def create_requirement(
    db: AsyncSession, organization_id: int, **kwargs,
) -> DealStageRequirement:
    req = DealStageRequirement(organization_id=organization_id, **kwargs)
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


async def list_requirements(
    db: AsyncSession, organization_id: int, stage: str | None = None,
) -> list[DealStageRequirement]:
    q = select(DealStageRequirement).where(
        DealStageRequirement.organization_id == organization_id,
        DealStageRequirement.is_active.is_(True),
    )
    if stage:
        q = q.where(DealStageRequirement.stage == stage)
    q = q.order_by(DealStageRequirement.stage, DealStageRequirement.sort_order)
    result = await db.execute(q)
    return list(result.scalars().all())


async def delete_requirement(
    db: AsyncSession, req_id: int, organization_id: int,
) -> bool:
    result = await db.execute(
        select(DealStageRequirement).where(
            DealStageRequirement.id == req_id,
            DealStageRequirement.organization_id == organization_id,
        )
    )
    req = result.scalar_one_or_none()
    if req is None:
        return False
    req.is_active = False
    await db.commit()
    return True


async def check_requirement(
    db: AsyncSession, deal_id: int, requirement_id: int, user_id: int | None = None, notes: str | None = None,
) -> DealRequirementCheck:
    """Mark a requirement as completed for a deal."""
    result = await db.execute(
        select(DealRequirementCheck).where(
            DealRequirementCheck.deal_id == deal_id,
            DealRequirementCheck.requirement_id == requirement_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.is_completed = True
        existing.completed_by_user_id = user_id
        existing.completed_at = datetime.now(UTC)
        existing.notes = notes
        await db.commit()
        await db.refresh(existing)
        return existing

    check = DealRequirementCheck(
        deal_id=deal_id,
        requirement_id=requirement_id,
        is_completed=True,
        completed_by_user_id=user_id,
        completed_at=datetime.now(UTC),
        notes=notes,
    )
    db.add(check)
    await db.commit()
    await db.refresh(check)
    return check


async def get_deal_checklist(
    db: AsyncSession, deal_id: int, stage: str, organization_id: int,
) -> list[dict]:
    """Get all requirements for a stage with completion status for a deal."""
    reqs = await list_requirements(db, organization_id, stage=stage)
    if not reqs:
        return []

    req_ids = [r.id for r in reqs]
    result = await db.execute(
        select(DealRequirementCheck).where(
            DealRequirementCheck.deal_id == deal_id,
            DealRequirementCheck.requirement_id.in_(req_ids),
        )
    )
    checks = {c.requirement_id: c for c in result.scalars().all()}

    checklist = []
    for req in reqs:
        check = checks.get(req.id)
        checklist.append({
            "requirement_id": req.id,
            "title": req.title,
            "description": req.description,
            "is_mandatory": req.is_mandatory,
            "is_completed": check.is_completed if check else False,
            "completed_at": check.completed_at.isoformat() if check and check.completed_at else None,
        })
    return checklist


async def validate_stage_entry(
    db: AsyncSession, deal_id: int, stage: str, organization_id: int,
) -> dict:
    """Check if all mandatory requirements for a stage are met."""
    checklist = await get_deal_checklist(db, deal_id, stage, organization_id)
    mandatory_incomplete = [
        item for item in checklist
        if item["is_mandatory"] and not item["is_completed"]
    ]
    return {
        "stage": stage,
        "can_enter": len(mandatory_incomplete) == 0,
        "total_requirements": len(checklist),
        "completed": sum(1 for i in checklist if i["is_completed"]),
        "blocking": [i["title"] for i in mandatory_incomplete],
    }
