from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContactMergeHistory(Base):
    """Tracks contact merge operations for audit and undo."""

    __tablename__ = "contact_merge_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    primary_contact_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    merged_contact_id: Mapped[int] = mapped_column(Integer, nullable=False)
    merged_contact_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    primary_before_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    undone: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
