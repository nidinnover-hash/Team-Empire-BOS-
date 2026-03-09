"""Revenue recognition model — recognized vs deferred by period."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RevenueEntry(Base):
    __tablename__ = "revenue_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    deal_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    period: Mapped[str] = mapped_column(String(10), nullable=False)  # "2026-03", "2026-Q1"
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    recognized_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    deferred_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recognition_stage: Mapped[str] = mapped_column(String(30), nullable=False, default="contract")  # contract, delivery, acceptance, billing, complete
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
