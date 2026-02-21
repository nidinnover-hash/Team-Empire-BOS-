from datetime import datetime, timezone
from sqlalchemy import Text, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Command(Base):
    """Every command the user sends plus the AI's reply."""

    __tablename__ = "commands"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    command_text: Mapped[str] = mapped_column(Text, nullable=False)
    ai_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
