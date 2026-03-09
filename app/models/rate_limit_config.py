"""API rate limiting config model — per-org configurable limits."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RateLimitConfig(Base):
    __tablename__ = "rate_limit_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    endpoint_pattern: Mapped[str] = mapped_column(String(200), nullable=False)  # glob pattern e.g. "/api/v1/contacts*"
    requests_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    requests_per_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    burst_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    total_requests_tracked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_throttled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
