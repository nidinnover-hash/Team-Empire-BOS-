from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"
    __table_args__ = (
        UniqueConstraint("organization_id", "url", name="uq_webhook_org_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    event_types: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    max_retry_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        return f"<WebhookEndpoint id={self.id} url={self.url!r} active={self.is_active}>"


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    webhook_endpoint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True,
    )
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True,
    )
    max_retries: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )

    def __repr__(self) -> str:
        return f"<WebhookDelivery id={self.id} event={self.event!r} status={self.status!r}>"
