from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base



class Email(Base):
    __tablename__ = "emails"
    __table_args__ = (
        UniqueConstraint("organization_id", "gmail_id", name="uq_emails_org_gmail_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    gmail_id: Mapped[str] = mapped_column(String(200), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    from_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    to_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    gmail_draft_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    approval_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reply_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reply_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
