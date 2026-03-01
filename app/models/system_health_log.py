"""System health log — tracks API errors, sync failures, and degraded states."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemHealthLog(Base):
    __tablename__ = "system_health_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    category: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True,
    )  # api_error, sync_failure, ai_fallback, slow_query, scheduler_error
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="warning",
    )  # info, warning, error, critical
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True,
    )
