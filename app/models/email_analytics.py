"""Email analytics model — open/click/reply tracking."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailEvent(Base):
    __tablename__ = "email_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    email_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    contact_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)  # sent, delivered, opened, clicked, replied, bounced
    link_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
