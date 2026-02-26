from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinanceEntry(Base):
    """An income or expense record for personal/business finance tracking."""

    __tablename__ = "finance_entries"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_finance_positive_amount"),
        CheckConstraint("type IN ('income', 'expense')", name="ck_finance_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # income | expense
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    # salary | freelance | food | transport | housing | health | entertainment | other
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

