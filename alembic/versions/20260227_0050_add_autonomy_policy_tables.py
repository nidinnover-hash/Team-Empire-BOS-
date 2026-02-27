"""add autonomy policy config + version tables

Revision ID: 20260227_0050
Revises: 20260226_0042
Create Date: 2026-02-27
"""
from alembic import op
import sqlalchemy as sa

revision = "20260227_0050"
down_revision = "20260226_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autonomy_policy_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("current_mode", sa.String(length=32), nullable=False, server_default="approved_execution"),
        sa.Column("allow_auto_approval", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("min_readiness_for_auto_approval", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("min_readiness_for_approved_execution", sa.Integer(), nullable=False, server_default="65"),
        sa.Column("min_readiness_for_autonomous", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("block_on_unread_high_alerts", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("block_on_stale_integrations", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("block_on_sla_breaches", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("kill_switch", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("pilot_org_ids_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("max_actions_per_day", sa.Integer(), nullable=False, server_default="250"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id"),
    )
    op.create_index(
        "ix_autonomy_policy_configs_organization_id",
        "autonomy_policy_configs",
        ["organization_id"],
    )
    op.create_index(
        "ix_autonomy_policy_configs_updated_at",
        "autonomy_policy_configs",
        ["updated_at"],
    )
    op.create_index(
        "ix_autonomy_policy_configs_updated_by_user_id",
        "autonomy_policy_configs",
        ["updated_by_user_id"],
    )

    op.create_table(
        "autonomy_policy_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=False),
        sa.Column("policy_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("rollback_of_version_id", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_email", sa.String(length=320), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_autonomy_policy_versions_organization_id",
        "autonomy_policy_versions",
        ["organization_id"],
    )
    op.create_index(
        "ix_autonomy_policy_versions_updated_at",
        "autonomy_policy_versions",
        ["updated_at"],
    )
    op.create_index(
        "ix_autonomy_policy_versions_updated_by_user_id",
        "autonomy_policy_versions",
        ["updated_by_user_id"],
    )
    op.create_index(
        "ix_autonomy_policy_versions_version_id",
        "autonomy_policy_versions",
        ["version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_autonomy_policy_versions_version_id", table_name="autonomy_policy_versions")
    op.drop_index("ix_autonomy_policy_versions_updated_by_user_id", table_name="autonomy_policy_versions")
    op.drop_index("ix_autonomy_policy_versions_updated_at", table_name="autonomy_policy_versions")
    op.drop_index("ix_autonomy_policy_versions_organization_id", table_name="autonomy_policy_versions")
    op.drop_table("autonomy_policy_versions")

    op.drop_index("ix_autonomy_policy_configs_updated_by_user_id", table_name="autonomy_policy_configs")
    op.drop_index("ix_autonomy_policy_configs_updated_at", table_name="autonomy_policy_configs")
    op.drop_index("ix_autonomy_policy_configs_organization_id", table_name="autonomy_policy_configs")
    op.drop_table("autonomy_policy_configs")
