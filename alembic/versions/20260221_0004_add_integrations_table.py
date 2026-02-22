"""add integrations table

Revision ID: 20260221_0004
Revises: 20260221_0003
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260221_0004"
down_revision = "20260221_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="connected"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "type", name="uq_integrations_org_type"),
    )
    op.create_index("ix_integrations_organization_id", "integrations", ["organization_id"], unique=False)
    op.create_index("ix_integrations_type", "integrations", ["type"], unique=False)
    op.create_index("ix_integrations_status", "integrations", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_integrations_status", table_name="integrations")
    op.drop_index("ix_integrations_type", table_name="integrations")
    op.drop_index("ix_integrations_organization_id", table_name="integrations")
    op.drop_table("integrations")
