"""Dashboard widget library — reusable widget definitions for dashboard customization."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DashboardWidget(Base):
    __tablename__ = "dashboard_widgets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    widget_type: Mapped[str] = mapped_column(String(50), nullable=False)  # chart, metric, table, list
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    data_source: Mapped[str] = mapped_column(String(100), nullable=False)  # deals, tasks, contacts, finance
    default_width: Mapped[int] = mapped_column(Integer, nullable=False, default=4)  # grid columns
    default_height: Mapped[int] = mapped_column(Integer, nullable=False, default=3)  # grid rows
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # built-in vs custom
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
