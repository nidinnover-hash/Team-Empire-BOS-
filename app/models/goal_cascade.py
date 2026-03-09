"""Goal cascade model — link company goals to team goals to individual quotas."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoalCascadeLink(Base):
    __tablename__ = "goal_cascade_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    parent_type: Mapped[str] = mapped_column(String(30), nullable=False)  # goal, key_result
    parent_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    child_type: Mapped[str] = mapped_column(String(30), nullable=False)  # goal, key_result, quota
    child_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)  # contribution weight
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
