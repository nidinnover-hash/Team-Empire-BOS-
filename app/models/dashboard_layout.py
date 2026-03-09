"""Dashboard layout model — per-user widget configuration."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DEFAULT_WIDGETS = [
    {"id": "kpis", "title": "Key Metrics", "x": 0, "y": 0, "w": 12, "h": 2},
    {"id": "trends", "title": "Trends", "x": 0, "y": 2, "w": 8, "h": 4},
    {"id": "tasks", "title": "Pending Tasks", "x": 8, "y": 2, "w": 4, "h": 4},
    {"id": "deals", "title": "Deal Pipeline", "x": 0, "y": 6, "w": 6, "h": 3},
    {"id": "activity", "title": "Recent Activity", "x": 6, "y": 6, "w": 6, "h": 3},
]


class DashboardLayout(Base):
    __tablename__ = "dashboard_layouts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    layout_json: Mapped[str] = mapped_column(Text, nullable=False)
    theme: Mapped[str] = mapped_column(String(20), nullable=False, default="default")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
