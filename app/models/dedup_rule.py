"""Contact deduplication rules model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DedupRule(Base):
    __tablename__ = "dedup_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    match_fields: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    merge_strategy: Mapped[str] = mapped_column(String(30), nullable=False, default="keep_newest")
    confidence_threshold: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0.8)
    auto_merge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    total_matches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_merges: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
