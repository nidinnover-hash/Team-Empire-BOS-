from __future__ import annotations

from sqlalchemy.sql import Select


def apply_org_scope(query: Select, model, org_id: int) -> Select:
    """
    Helper to enforce tenant filtering consistently on SQLAlchemy selects.
    Model must expose an organization_id column.
    """
    return query.where(model.organization_id == org_id)
