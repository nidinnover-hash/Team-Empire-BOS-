"""Competitor tracking model — per-deal competitive intelligence."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Competitor(Base):
    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    strengths: Mapped[str | None] = mapped_column(Text, nullable=True)
    weaknesses: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )


class DealCompetitor(Base):
    __tablename__ = "deal_competitors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    deal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    competitor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("competitors.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    threat_level: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")  # low, medium, high
    win_loss_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
