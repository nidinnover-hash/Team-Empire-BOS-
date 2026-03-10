"""Drip campaign analytics model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DripStepEvent(Base):
    __tablename__ = "drip_step_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    campaign_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    step_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    enrollment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    contact_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)  # sent, opened, clicked, bounced, unsubscribed
    metadata_json: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
