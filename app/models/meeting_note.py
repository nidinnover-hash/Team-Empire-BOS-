"""Meeting notes model — summaries linked to contacts/deals."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MeetingNote(Base):
    __tablename__ = "meeting_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # [{task, assignee, due}]
    contact_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    deal_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    meeting_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attendees_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
