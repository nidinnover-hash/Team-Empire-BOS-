"""User activity heatmap model — track login patterns and feature usage."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserActivityEntry(Base):
    __tablename__ = "user_activity_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # login, api_call, page_view, feature_use
    feature_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hour_of_day: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-23
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon, 6=Sun
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
