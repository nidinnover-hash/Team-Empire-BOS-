"""Deal collaboration model — multiple team members per deal."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DealCollaborator(Base):
    __tablename__ = "deal_collaborators"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    deal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="support")  # owner, support, reviewer, observer
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
