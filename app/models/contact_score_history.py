"""Contact scoring history model — track how lead scores change over time."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContactScoreSnapshot(Base):
    __tablename__ = "contact_score_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    contact_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    change_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")  # manual, rule, decay, enrichment
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
