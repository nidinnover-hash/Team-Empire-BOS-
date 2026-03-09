from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KeyResult(Base):
    """A measurable key result linked to a goal (OKR pattern)."""

    __tablename__ = "key_results"
    __table_args__ = (
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_kr_progress"),
        CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')",
            name="ck_kr_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    goal_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "$", "%", "users"
    target_value: Mapped[float] = mapped_column(Float, default=100.0)
    current_value: Mapped[float] = mapped_column(Float, default=0.0)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100, auto-calculated
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
