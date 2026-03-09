"""Document template service — proposals/contracts with merge fields."""
from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_template import DocumentTemplate


async def create_template(
    db: AsyncSession, *, organization_id: int, name: str,
    doc_type: str, content: str, merge_fields: list[str] | None = None,
    created_by_user_id: int | None = None,
) -> DocumentTemplate:
    row = DocumentTemplate(
        organization_id=organization_id, name=name,
        doc_type=doc_type, content=content,
        merge_fields_json=json.dumps(merge_fields or []),
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_templates(
    db: AsyncSession, organization_id: int, *,
    doc_type: str | None = None, is_active: bool | None = None,
) -> list[DocumentTemplate]:
    q = select(DocumentTemplate).where(DocumentTemplate.organization_id == organization_id)
    if doc_type:
        q = q.where(DocumentTemplate.doc_type == doc_type)
    if is_active is not None:
        q = q.where(DocumentTemplate.is_active == is_active)
    q = q.order_by(DocumentTemplate.updated_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_template(db: AsyncSession, template_id: int, organization_id: int) -> DocumentTemplate | None:
    q = select(DocumentTemplate).where(
        DocumentTemplate.id == template_id,
        DocumentTemplate.organization_id == organization_id,
    )
    return (await db.execute(q)).scalar_one_or_none()


async def update_template(db: AsyncSession, template_id: int, organization_id: int, **kwargs) -> DocumentTemplate | None:
    row = await get_template(db, template_id, organization_id)
    if not row:
        return None
    if "merge_fields" in kwargs:
        kwargs["merge_fields_json"] = json.dumps(kwargs.pop("merge_fields") or [])
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    row.version += 1
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


async def render_template(db: AsyncSession, template_id: int, organization_id: int, data: dict) -> dict | None:
    row = await get_template(db, template_id, organization_id)
    if not row:
        return None
    rendered = row.content
    for key, value in data.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
    # Find unresolved fields
    unresolved = re.findall(r"\{\{(\w+)\}\}", rendered)
    return {"rendered": rendered, "unresolved_fields": unresolved}
