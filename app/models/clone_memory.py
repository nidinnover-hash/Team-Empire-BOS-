"""Clone memory entries — stores successful interaction patterns for RAG-lite retrieval."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CloneMemoryEntry(Base):
    __tablename__ = "clone_memory_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # What happened
    situation: Mapped[str] = mapped_column(Text, nullable=False)
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(
        String(30), nullable=False,
    )  # success, partial, failure
    outcome_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Classification
    category: Mapped[str] = mapped_column(
        String(40), nullable=False, default="general",
    )  # sales, support, operations, onboarding, negotiation
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Memory quality
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    reinforcement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_retrieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Source traceability
    source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
