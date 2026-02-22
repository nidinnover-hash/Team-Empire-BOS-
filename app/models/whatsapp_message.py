from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"
    __table_args__ = (
        UniqueConstraint("organization_id", "wa_message_id", name="uq_wa_messages_org_message_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    integration_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("integrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    wa_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    wa_contact_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # inbound|outbound
    from_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    to_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    message_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
