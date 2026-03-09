"""Contact scoring rule model — configurable rules for lead scoring."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RULE_FIELDS = (
    "company", "role", "lead_source", "pipeline_stage", "source_channel",
    "campaign_name", "tags", "relationship",
)
RULE_OPERATORS = ("contains", "equals", "starts_with", "not_empty")


class ScoringRule(Base):
    __tablename__ = "scoring_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    field: Mapped[str] = mapped_column(String(50), nullable=False)  # contact field to check
    operator: Mapped[str] = mapped_column(String(30), nullable=False)  # contains, equals, etc.
    value: Mapped[str] = mapped_column(String(500), nullable=False, default="")  # value to match
    score_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=10)  # points to add/subtract
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
