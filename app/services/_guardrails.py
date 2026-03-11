"""Shared service-layer guardrails for tenant scoping and safe updates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def tenant_select(model: type[Any], organization_id: int, *, org_field: str = "organization_id"):
    """Return a tenant-scoped SELECT statement for a model."""
    return select(model).where(getattr(model, org_field) == organization_id)


async def get_tenant_row(
    db: AsyncSession,
    model: type[Any],
    row_id: int,
    organization_id: int,
    *,
    id_field: str = "id",
    org_field: str = "organization_id",
):
    """Fetch a row by ID constrained to one tenant."""
    result = await db.execute(
        select(model).where(
            getattr(model, id_field) == row_id,
            getattr(model, org_field) == organization_id,
        )
    )
    return result.scalar_one_or_none()


def apply_safe_updates(
    instance: Any,
    updates: Mapping[str, Any],
    *,
    protected_fields: Iterable[str],
    allowed_fields: Iterable[str] | None = None,
    skip_none: bool = False,
) -> list[str]:
    """Apply safe field updates to an ORM instance.

    - never applies protected fields
    - optionally restricts to an explicit allow-list
    - optionally skips None values
    """
    protected = set(protected_fields)
    allowed = set(allowed_fields) if allowed_fields is not None else None
    changed: list[str] = []
    for key, value in updates.items():
        if key in protected:
            continue
        if allowed is not None and key not in allowed:
            continue
        if skip_none and value is None:
            continue
        if hasattr(instance, key):
            setattr(instance, key, value)
            changed.append(key)
    return changed

