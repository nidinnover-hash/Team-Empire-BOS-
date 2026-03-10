"""Referral program model — sources, tracking codes, rewards."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReferralSource(Base):
    __tablename__ = "referral_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tracking_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    reward_type: Mapped[str] = mapped_column(String(30), nullable=False, default="flat")  # flat, percent, credit
    reward_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_referrals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_conversions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_rewards_paid: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("referral_sources.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    contact_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    deal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending, converted, expired
    reward_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
