"""Email suppression model — blacklist, bounces, domain blocks."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailSuppression(Base):
    __tablename__ = "email_suppressions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    email_or_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    suppression_type: Mapped[str] = mapped_column(String(30), nullable=False)  # bounce, complaint, manual, domain
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")  # manual, webhook, import
    bounce_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
