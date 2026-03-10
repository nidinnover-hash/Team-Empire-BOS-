"""Customer onboarding checklist service."""
from __future__ import annotations

import json

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.onboarding_checklist import OnboardingTemplate, OnboardingChecklist


async def create_template(
    db: AsyncSession, *, organization_id: int, name: str,
    description: str | None = None, steps: list[dict] | None = None,
    is_active: bool = True,
) -> OnboardingTemplate:
    row = OnboardingTemplate(
        organization_id=organization_id, name=name,
        description=description, steps_json=json.dumps(steps or []),
        is_active=is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_templates(db: AsyncSession, organization_id: int, *, is_active: bool | None = None) -> list[OnboardingTemplate]:
    q = select(OnboardingTemplate).where(OnboardingTemplate.organization_id == organization_id)
    if is_active is not None:
        q = q.where(OnboardingTemplate.is_active == is_active)
    q = q.order_by(OnboardingTemplate.name)
    return list((await db.execute(q)).scalars().all())


async def get_template(db: AsyncSession, template_id: int, organization_id: int) -> OnboardingTemplate | None:
    q = select(OnboardingTemplate).where(OnboardingTemplate.id == template_id, OnboardingTemplate.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_template(db: AsyncSession, template_id: int, organization_id: int, **kwargs) -> OnboardingTemplate | None:
    row = await get_template(db, template_id, organization_id)
    if not row:
        return None
    if "steps" in kwargs:
        kwargs["steps_json"] = json.dumps(kwargs.pop("steps") or [])
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_template(db: AsyncSession, template_id: int, organization_id: int) -> bool:
    row = await get_template(db, template_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def assign_checklist(
    db: AsyncSession, *, organization_id: int, template_id: int,
    contact_id: int | None = None, deal_id: int | None = None,
    assigned_user_id: int | None = None,
) -> OnboardingChecklist:
    template = await get_template(db, template_id, organization_id)
    total = len(json.loads(template.steps_json)) if template else 0
    row = OnboardingChecklist(
        organization_id=organization_id, template_id=template_id,
        contact_id=contact_id, deal_id=deal_id,
        assigned_user_id=assigned_user_id, total_steps=total,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_checklists(
    db: AsyncSession, organization_id: int, *,
    status: str | None = None, contact_id: int | None = None,
) -> list[OnboardingChecklist]:
    q = select(OnboardingChecklist).where(OnboardingChecklist.organization_id == organization_id)
    if status:
        q = q.where(OnboardingChecklist.status == status)
    if contact_id is not None:
        q = q.where(OnboardingChecklist.contact_id == contact_id)
    q = q.order_by(OnboardingChecklist.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_checklist(db: AsyncSession, checklist_id: int, organization_id: int) -> OnboardingChecklist | None:
    q = select(OnboardingChecklist).where(OnboardingChecklist.id == checklist_id, OnboardingChecklist.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def complete_step(
    db: AsyncSession, checklist_id: int, organization_id: int, step_index: int,
) -> OnboardingChecklist | None:
    row = await get_checklist(db, checklist_id, organization_id)
    if not row:
        return None
    progress = json.loads(row.progress_json)
    progress[str(step_index)] = True
    row.progress_json = json.dumps(progress)
    row.completed_steps = sum(1 for v in progress.values() if v)
    if row.completed_steps >= row.total_steps and row.total_steps > 0:
        row.status = "completed"
    await db.commit()
    await db.refresh(row)
    return row
