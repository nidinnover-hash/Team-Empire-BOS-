"""Email template service — CRUD and rendering."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_template import EmailTemplate


async def create_template(
    db: AsyncSession, organization_id: int, created_by_user_id: int | None = None, **kwargs,
) -> EmailTemplate:
    if "variables" in kwargs:
        kwargs["variables_json"] = json.dumps(kwargs.pop("variables"))
    tmpl = EmailTemplate(
        organization_id=organization_id,
        created_by_user_id=created_by_user_id,
        **kwargs,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


async def list_templates(
    db: AsyncSession, organization_id: int, category: str | None = None,
) -> list[EmailTemplate]:
    q = select(EmailTemplate).where(
        EmailTemplate.organization_id == organization_id,
        EmailTemplate.is_active.is_(True),
    )
    if category:
        q = q.where(EmailTemplate.category == category)
    q = q.order_by(EmailTemplate.id.desc())
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_template(
    db: AsyncSession, template_id: int, organization_id: int,
) -> EmailTemplate | None:
    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.id == template_id,
            EmailTemplate.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def update_template(
    db: AsyncSession, template_id: int, organization_id: int, **kwargs,
) -> EmailTemplate | None:
    tmpl = await get_template(db, template_id, organization_id)
    if tmpl is None:
        return None
    if "variables" in kwargs:
        kwargs["variables_json"] = json.dumps(kwargs.pop("variables"))
    for k, v in kwargs.items():
        if v is not None and hasattr(tmpl, k):
            setattr(tmpl, k, v)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


async def delete_template(
    db: AsyncSession, template_id: int, organization_id: int,
) -> bool:
    tmpl = await get_template(db, template_id, organization_id)
    if tmpl is None:
        return False
    tmpl.is_active = False
    await db.commit()
    return True


def render_template(body: str, subject: str, variables: dict[str, str]) -> dict:
    """Render a template with variable substitution. Variables use {{name}} syntax."""
    rendered_body = body
    rendered_subject = subject
    for key, value in variables.items():
        pattern = r"\{\{\s*" + re.escape(key) + r"\s*\}\}"
        rendered_body = re.sub(pattern, str(value), rendered_body)
        rendered_subject = re.sub(pattern, str(value), rendered_subject)
    return {"subject": rendered_subject, "body": rendered_body}
