"""Custom field service — manage definitions and values."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_field import CustomFieldDefinition, CustomFieldValue


async def create_definition(
    db: AsyncSession, organization_id: int, **kwargs,
) -> CustomFieldDefinition:
    if "options" in kwargs and kwargs["options"]:
        kwargs["options_json"] = json.dumps(kwargs.pop("options"))
    else:
        kwargs.pop("options", None)
    defn = CustomFieldDefinition(organization_id=organization_id, **kwargs)
    db.add(defn)
    await db.commit()
    await db.refresh(defn)
    return defn


async def list_definitions(
    db: AsyncSession, organization_id: int, entity_type: str | None = None,
) -> list[CustomFieldDefinition]:
    q = select(CustomFieldDefinition).where(
        CustomFieldDefinition.organization_id == organization_id,
        CustomFieldDefinition.is_active.is_(True),
    )
    if entity_type:
        q = q.where(CustomFieldDefinition.entity_type == entity_type)
    q = q.order_by(CustomFieldDefinition.sort_order, CustomFieldDefinition.id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_definition(
    db: AsyncSession, defn_id: int, organization_id: int, **kwargs,
) -> CustomFieldDefinition | None:
    result = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.id == defn_id,
            CustomFieldDefinition.organization_id == organization_id,
        )
    )
    defn = result.scalar_one_or_none()
    if defn is None:
        return None
    if "options" in kwargs and kwargs["options"] is not None:
        kwargs["options_json"] = json.dumps(kwargs.pop("options"))
    else:
        kwargs.pop("options", None)
    for k, v in kwargs.items():
        if v is not None and hasattr(defn, k):
            setattr(defn, k, v)
    await db.commit()
    await db.refresh(defn)
    return defn


async def delete_definition(
    db: AsyncSession, defn_id: int, organization_id: int,
) -> bool:
    result = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.id == defn_id,
            CustomFieldDefinition.organization_id == organization_id,
        )
    )
    defn = result.scalar_one_or_none()
    if defn is None:
        return False
    defn.is_active = False
    await db.commit()
    return True


async def set_value(
    db: AsyncSession, field_definition_id: int, entity_id: int, value: str,
) -> CustomFieldValue:
    result = await db.execute(
        select(CustomFieldValue).where(
            CustomFieldValue.field_definition_id == field_definition_id,
            CustomFieldValue.entity_id == entity_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value_text = value
        existing.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(existing)
        return existing

    val = CustomFieldValue(
        field_definition_id=field_definition_id,
        entity_id=entity_id,
        value_text=value,
    )
    db.add(val)
    await db.commit()
    await db.refresh(val)
    return val


async def get_values(
    db: AsyncSession, entity_type: str, entity_id: int, organization_id: int,
) -> list[dict]:
    """Get all custom field values for an entity."""
    result = await db.execute(
        select(CustomFieldDefinition, CustomFieldValue)
        .outerjoin(
            CustomFieldValue,
            (CustomFieldValue.field_definition_id == CustomFieldDefinition.id)
            & (CustomFieldValue.entity_id == entity_id),
        )
        .where(
            CustomFieldDefinition.organization_id == organization_id,
            CustomFieldDefinition.entity_type == entity_type,
            CustomFieldDefinition.is_active.is_(True),
        )
        .order_by(CustomFieldDefinition.sort_order)
    )
    rows = result.all()
    return [
        {
            "field_id": defn.id,
            "field_key": defn.field_key,
            "field_label": defn.field_label,
            "field_type": defn.field_type,
            "value": val.value_text if val else None,
        }
        for defn, val in rows
    ]
