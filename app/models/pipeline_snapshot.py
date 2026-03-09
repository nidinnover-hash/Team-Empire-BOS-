"""Pipeline snapshot model — periodic state captures for trend analysis."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PipelineSnapshot(Base):
    __tablename__ = "pipeline_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    snapshot_type: Mapped[str] = mapped_column(String(20), nullable=False, default="daily")  # daily, weekly
    total_deals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage_breakdown_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    weighted_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_deals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    won_deals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lost_deals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
