from datetime import datetime, timezone
from sqlalchemy import Text, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Note(Base):
    """Quick memory snippet with optional title and comma-separated tags."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # e.g. "work,idea,urgent"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
