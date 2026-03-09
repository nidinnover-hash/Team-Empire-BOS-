"""Contact score decay model — rules for automatic score reduction."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScoreDecayRule(Base):
    __tablename__ = "score_decay_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    inactive_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    decay_points: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    min_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="daily")  # daily, weekly
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contacts_affected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
