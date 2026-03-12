"""Add org optimistic concurrency fields and critical performance indexes.

Revision ID: 20260301_0059
Revises: 20260301_0058
Create Date: 2026-03-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260301_0059"
down_revision = "20260301_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_org = {c["name"] for c in inspector.get_columns("organizations")}
    if "config_version" not in existing_org:
        op.add_column(
            "organizations",
            sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        )
    if "updated_at" not in existing_org:
        op.add_column(
            "organizations",
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    existing_apr_idxs = {i["name"] for i in inspector.get_indexes("approvals")}
    if "ix_approvals_org_status_created_at" not in existing_apr_idxs:
        op.create_index(
            "ix_approvals_org_status_created_at",
            "approvals",
            ["organization_id", "status", "created_at"],
        )
    if "ix_approvals_created_at" not in existing_apr_idxs:
        op.create_index("ix_approvals_created_at", "approvals", ["created_at"])

    existing_int_idxs = {i["name"] for i in inspector.get_indexes("integrations")}
    if "ix_integrations_org_status_last_sync_at" not in existing_int_idxs:
        op.create_index(
            "ix_integrations_org_status_last_sync_at",
            "integrations",
            ["organization_id", "status", "last_sync_at"],
        )
    if "ix_integrations_last_sync_status" not in existing_int_idxs:
        op.create_index("ix_integrations_last_sync_status", "integrations", ["last_sync_status"])

    existing_evt_idxs = {i["name"] for i in inspector.get_indexes("events")}
    if "ix_events_org_event_type_created_at" not in existing_evt_idxs:
        op.create_index(
            "ix_events_org_event_type_created_at",
            "events",
            ["organization_id", "event_type", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_events_org_event_type_created_at", table_name="events")
    op.drop_index("ix_integrations_last_sync_status", table_name="integrations")
    op.drop_index("ix_integrations_org_status_last_sync_at", table_name="integrations")
    op.drop_index("ix_approvals_created_at", table_name="approvals")
    op.drop_index("ix_approvals_org_status_created_at", table_name="approvals")
    op.drop_column("organizations", "updated_at")
    op.drop_column("organizations", "config_version")
