"""Recurring invoice model — scheduled invoice generation from templates."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RecurringInvoice(Base):
    __tablename__ = "recurring_invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    contact_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)  # weekly, monthly, quarterly, yearly
    line_items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    next_due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
