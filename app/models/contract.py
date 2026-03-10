"""Contract tracking model — lifecycle, renewals, reminders."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    deal_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    contact_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")  # draft, sent, signed, expired, cancelled
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renewal_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_renew: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0=no, 1=yes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
