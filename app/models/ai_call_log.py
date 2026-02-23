from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiCallLog(Base):
    """Record of every AI provider call for observability — latency, tokens, fallbacks."""
    __tablename__ = "ai_call_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fallback_from: Mapped[str | None] = mapped_column(String(30), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
