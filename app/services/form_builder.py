"""Form builder service."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.form_builder import FormDefinition, FormSubmission


async def create_form(
    db: AsyncSession, *, organization_id: int, name: str,
    description: str | None = None, fields: list[dict] | None = None,
    redirect_url: str | None = None, confirmation_message: str | None = None,
    created_by_user_id: int | None = None,
) -> FormDefinition:
    row = FormDefinition(
        organization_id=organization_id, name=name, description=description,
        fields_json=json.dumps(fields or []),
        redirect_url=redirect_url, confirmation_message=confirmation_message,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_forms(
    db: AsyncSession, organization_id: int, *, is_active: bool | None = None,
) -> list[FormDefinition]:
    q = select(FormDefinition).where(FormDefinition.organization_id == organization_id)
    if is_active is not None:
        q = q.where(FormDefinition.is_active == is_active)
    q = q.order_by(FormDefinition.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_form(db: AsyncSession, form_id: int, organization_id: int) -> FormDefinition | None:
    q = select(FormDefinition).where(FormDefinition.id == form_id, FormDefinition.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_form(db: AsyncSession, form_id: int, organization_id: int, **kwargs) -> FormDefinition | None:
    row = await get_form(db, form_id, organization_id)
    if not row:
        return None
    if "fields" in kwargs:
        kwargs["fields_json"] = json.dumps(kwargs.pop("fields") or [])
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_form(db: AsyncSession, form_id: int, organization_id: int) -> bool:
    row = await get_form(db, form_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def submit_form(
    db: AsyncSession, *, form_id: int, organization_id: int,
    data: dict, contact_id: int | None = None, source_ip: str | None = None,
) -> FormSubmission:
    sub = FormSubmission(
        form_id=form_id, organization_id=organization_id,
        data_json=json.dumps(data), contact_id=contact_id, source_ip=source_ip,
    )
    db.add(sub)
    # Increment submission count
    form = await get_form(db, form_id, organization_id)
    if form:
        form.total_submissions += 1
    await db.commit()
    await db.refresh(sub)
    return sub


async def list_submissions(
    db: AsyncSession, form_id: int, organization_id: int, *, limit: int = 50,
) -> list[FormSubmission]:
    q = (
        select(FormSubmission)
        .where(FormSubmission.form_id == form_id, FormSubmission.organization_id == organization_id)
        .order_by(FormSubmission.created_at.desc())
        .limit(limit)
    )
    return list((await db.execute(q)).scalars().all())
