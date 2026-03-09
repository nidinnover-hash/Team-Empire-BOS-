"""Deal risk scoring model — automatic risk assessment."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DealRiskScore(Base):
    __tablename__ = "deal_risk_scores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    deal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="low")  # low, medium, high, critical
    factors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
