"""Email sequence automation model — multi-step drip campaigns."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailSequence(Base):
    __tablename__ = "email_sequences"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_event: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "contact.created", "deal.stage_changed"
    exit_condition: Mapped[str | None] = mapped_column(String(200), nullable=True)  # e.g. "replied", "unsubscribed"
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    total_enrolled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )


class EmailSequenceStep(Base):
    __tablename__ = "email_sequence_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sequence_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("email_sequences.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    delay_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
