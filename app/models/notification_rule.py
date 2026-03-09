"""Notification rule model — configurable rules for event-to-notification routing."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationRule(Base):
    __tablename__ = "notification_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type_pattern: Mapped[str] = mapped_column(String(100), nullable=False)  # glob: "deal_*", "task_*", "*"
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")  # info, warning, critical
    channel: Mapped[str] = mapped_column(String(30), nullable=False, default="in_app")  # in_app, email, both
    target_roles: Mapped[str] = mapped_column(String(200), nullable=False, default="CEO,ADMIN")  # comma-sep roles
    target_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # specific user override
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
