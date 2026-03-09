"""Import/export preset service."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_export_preset import ImportExportPreset


async def create_preset(db: AsyncSession, organization_id: int, created_by: int | None = None, **kwargs) -> ImportExportPreset:
    if "column_mapping" in kwargs:
        kwargs["column_mapping_json"] = json.dumps(kwargs.pop("column_mapping"))
    if "config" in kwargs:
        kwargs["config_json"] = json.dumps(kwargs.pop("config"))
    preset = ImportExportPreset(organization_id=organization_id, created_by_user_id=created_by, **kwargs)
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


async def list_presets(
    db: AsyncSession, organization_id: int, direction: str | None = None, entity_type: str | None = None,
) -> list[ImportExportPreset]:
    q = select(ImportExportPreset).where(
        ImportExportPreset.organization_id == organization_id,
        ImportExportPreset.is_active.is_(True),
    )
    if direction:
        q = q.where(ImportExportPreset.direction == direction)
    if entity_type:
        q = q.where(ImportExportPreset.entity_type == entity_type)
    result = await db.execute(q.order_by(ImportExportPreset.id))
    return list(result.scalars().all())


async def delete_preset(db: AsyncSession, preset_id: int, organization_id: int) -> bool:
    result = await db.execute(
        select(ImportExportPreset).where(
            ImportExportPreset.id == preset_id, ImportExportPreset.organization_id == organization_id,
        )
    )
    preset = result.scalar_one_or_none()
    if not preset:
        return False
    preset.is_active = False
    await db.commit()
    return True
