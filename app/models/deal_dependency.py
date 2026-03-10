"""Deal dependency model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DealDependency(Base):
    __tablename__ = "deal_dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    deal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    depends_on_deal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    dependency_type: Mapped[str] = mapped_column(String(30), nullable=False, default="blocks")  # blocks, requires, related
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
