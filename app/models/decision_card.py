"""DecisionCard — workspace-level human-in-the-loop decisions."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DecisionCard(Base):
    """AI-proposed decision that requires human approval within a workspace."""
    __tablename__ = "decision_cards"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Decision content
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    context_summary: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]",
    )  # JSON array of {label, description, risk_level}
    recommendation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Category / urgency
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="general",
    )  # general | strategic | operational | financial | hr
    urgency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="normal",
    )  # low | normal | high | critical
    # Resolution
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
    )  # pending | decided | deferred | expired
    chosen_option: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decision_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    proposed_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Source tracking
    source_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )  # ai_agent | manual | automation | share_packet
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
