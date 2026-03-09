"""Contact relationship mapping model — track links between contacts."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContactRelationship(Base):
    __tablename__ = "contact_relationships"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    contact_a_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    contact_b_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)  # colleague, manager, referral, spouse, partner
    strength: Mapped[int] = mapped_column(Integer, nullable=False, default=50)  # 0-100
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
