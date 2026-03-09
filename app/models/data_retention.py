"""Data retention policy model — configurable auto-archive/purge rules."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DataRetentionPolicy(Base):
    __tablename__ = "data_retention_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # contact, deal, task, event
    action: Mapped[str] = mapped_column(String(20), nullable=False, default="archive")  # archive, purge
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    condition_field: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "status"
    condition_value: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "closed"
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_affected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
