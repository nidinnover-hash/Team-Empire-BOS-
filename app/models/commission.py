"""Commission calculator model — rules, splits, and payout tracking."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CommissionRule(Base):
    __tablename__ = "commission_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    deal_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # filter by deal type
    stage: Mapped[str | None] = mapped_column(String(50), nullable=True)  # filter by stage
    rate_percent: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    min_deal_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_deal_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )


class CommissionPayout(Base):
    __tablename__ = "commission_payouts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    rule_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    deal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    deal_value: Mapped[int] = mapped_column(Integer, nullable=False)
    commission_amount: Mapped[float] = mapped_column(Float, nullable=False)
    split_percent: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending, approved, paid
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
