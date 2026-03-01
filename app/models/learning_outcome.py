from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LearningOutcome(Base):
    """Tracks whether an AI coaching recommendation was applied and its outcome."""

    __tablename__ = "learning_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    coaching_report_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("coaching_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recommendation_text: Mapped[str] = mapped_column(String(500), nullable=False)
    was_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outcome_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
