"""Dead-letter entry — captures failed operations for inspection and retry."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

try:
    from sqlalchemy import JSON
except ImportError:  # pragma: no cover
    from sqlalchemy.types import JSON  # type: ignore[assignment]


class DeadLetterEntry(Base):
    __tablename__ = "dead_letter_entries"
    __table_args__ = (
        Index("ix_dead_letter_org_status", "organization_id", "status"),
        Index("ix_dead_letter_org_source_type", "organization_id", "source_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(
        String(30), nullable=False,
    )  # webhook, scheduler, workflow, signal
    source_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )  # e.g. webhook_delivery.id, job_name, workflow_run.id
    source_detail: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
    )  # e.g. endpoint URL, job function name
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
    )  # pending, retrying, resolved, archived
    resolved_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
