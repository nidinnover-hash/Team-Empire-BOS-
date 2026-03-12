"""Soft delete mixin for models that need reversible deletion."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column


class SoftDeleteMixin:
    """Add is_deleted + deleted_at to any model.

    Usage:
        class Contact(SoftDeleteMixin, Base):
            ...

    All list queries should filter: .where(Model.is_deleted.is_(False))
    """

    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0", index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )
