"""Contact lifecycle stage model — track progression through sales funnel."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

LIFECYCLE_STAGES = ["lead", "mql", "sql", "opportunity", "customer", "churned"]


class ContactLifecycleEvent(Base):
    __tablename__ = "contact_lifecycle_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    contact_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    from_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
