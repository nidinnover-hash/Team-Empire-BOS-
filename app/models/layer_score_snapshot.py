"""Layer score historical snapshots — stores weekly layer scores for trend analysis."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LayerScoreSnapshot(Base):
    __tablename__ = "layer_score_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "layer_name", "snapshot_date",
            name="uq_layer_score_snapshot_org_layer_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    layer_name: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True,
    )
