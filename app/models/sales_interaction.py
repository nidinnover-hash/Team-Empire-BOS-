"""Sales interaction tracking — every lead touchpoint, objection, and outcome."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SalesInteractionLog(Base):
    __tablename__ = "sales_interaction_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    # Interaction metadata
    interaction_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="call",
    )  # call, email, meeting, whatsapp, followup
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # What happened
    objection_encountered: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_given: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Outcome
    outcome: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending",
    )  # converted, lost, pending, deferred, no_response
    outcome_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    loss_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # AI analysis
    ai_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_suggested_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
