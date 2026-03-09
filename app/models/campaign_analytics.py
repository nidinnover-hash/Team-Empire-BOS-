"""Campaign analytics model — track opens, clicks, and conversions per step."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampaignEvent(Base):
    __tablename__ = "campaign_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("email_campaigns.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    step_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("campaign_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    enrollment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("campaign_enrollments.id", ondelete="SET NULL"),
        nullable=True,
    )
    contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True,
    )  # sent, opened, clicked, bounced, unsubscribed
    variant: Mapped[str | None] = mapped_column(String(10), nullable=True)  # A/B variant: "A" or "B"
    metadata_json: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
