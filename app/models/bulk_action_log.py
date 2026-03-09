"""Bulk action audit trail model — detailed logging for bulk operations."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BulkActionLog(Base):
    __tablename__ = "bulk_action_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)  # import, export, delete, update, merge
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # contact, deal, task
    total_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # affected IDs, error details
    rollback_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # for undo support
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")  # completed, partial, failed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
