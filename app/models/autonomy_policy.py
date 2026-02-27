from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AutonomyPolicyConfig(Base):
    __tablename__ = "autonomy_policy_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    current_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="approved_execution")
    allow_auto_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    min_readiness_for_auto_approval: Mapped[int] = mapped_column(Integer, nullable=False, default=70, server_default="70")
    min_readiness_for_approved_execution: Mapped[int] = mapped_column(Integer, nullable=False, default=65, server_default="65")
    min_readiness_for_autonomous: Mapped[int] = mapped_column(Integer, nullable=False, default=90, server_default="90")
    block_on_unread_high_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    block_on_stale_integrations: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    block_on_sla_breaches: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    kill_switch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    pilot_org_ids_json: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    max_actions_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=250, server_default="250")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )


class AutonomyPolicyVersion(Base):
    __tablename__ = "autonomy_policy_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    rollback_of_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
