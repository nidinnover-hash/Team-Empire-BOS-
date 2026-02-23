from __future__ import annotations

from sqlalchemy.sql import Select


def require_org_id(org_id: int) -> int:
    if org_id <= 0:
        raise ValueError(f"organization_id must be positive, got {org_id}")
    return org_id


def apply_org_scope(query: Select, model, org_id: int) -> Select:
    """
    Helper to enforce tenant filtering consistently on SQLAlchemy selects.
    Model must expose an organization_id column.
    """
    return query.where(model.organization_id == require_org_id(org_id))
