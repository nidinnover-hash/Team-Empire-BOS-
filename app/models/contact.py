from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PIPELINE_STAGES = ("new", "contacted", "qualified", "proposal", "negotiation", "won", "lost")
LEAD_SOURCES = ("manual", "social_media", "referral", "website", "email", "event", "other")


class Contact(Base):
    """A person in your network — personal contact or sales lead."""

    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint(
            "relationship IN ('personal', 'business', 'family', 'mentor', 'other')",
            name="ck_contact_relationship",
        ),
        CheckConstraint(
            "pipeline_stage IN ('new', 'contacted', 'qualified', 'proposal', 'negotiation', 'won', 'lost')",
            name="ck_contact_pipeline_stage",
        ),
        CheckConstraint(
            "lead_score >= 0 AND lead_score <= 100",
            name="ck_contact_lead_score",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    email: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # personal | business | family | mentor | other
    relationship: Mapped[str] = mapped_column(String(50), default="personal")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── CRM / Sales Pipeline ─────────────────────────────────────────────────
    pipeline_stage: Mapped[str] = mapped_column(String(30), default="new", index=True)
    lead_score: Mapped[int] = mapped_column(Integer, default=0)
    lead_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    deal_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # comma-separated

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
