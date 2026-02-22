from datetime import datetime, timezone, date
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Goal(Base):
    """A long-term goal with progress tracking (0-100%)."""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # personal | business | health | finance | learning | other
    category: Mapped[str] = mapped_column(String(50), default="personal")
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # active | completed | paused | abandoned
    status: Mapped[str] = mapped_column(String(50), default="active")
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

