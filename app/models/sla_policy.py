"""SLA policy model — response/resolution time targets with breach tracking."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SlaPolicy(Base):
    __tablename__ = "sla_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # deal, task
    target_field: Mapped[str] = mapped_column(String(50), nullable=False)  # stage, priority
    target_value: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "proposal", "1"
    response_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )


class SlaBreach(Base):
    __tablename__ = "sla_breaches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    policy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sla_policies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    breach_type: Mapped[str] = mapped_column(String(20), nullable=False)  # response, resolution
    breached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
