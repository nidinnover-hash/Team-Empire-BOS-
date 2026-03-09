"""Duplicate detection model — track potential duplicate contacts/deals."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DuplicateMatch(Base):
    __tablename__ = "duplicate_matches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # contact, deal
    entity_a_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    entity_b_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    match_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100
    match_fields: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list of matched fields
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending, merged, dismissed
    resolved_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
