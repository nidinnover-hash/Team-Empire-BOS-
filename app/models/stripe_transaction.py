"""Stripe transaction persistence — charges, refunds, disputes linked to contacts."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StripeTransaction(Base):
    __tablename__ = "stripe_transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    stripe_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # charge | refund | dispute
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="usd")
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    stripe_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
