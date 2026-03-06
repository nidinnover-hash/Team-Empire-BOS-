"""Create signals table for BOS internal operating-system signals.

Revision ID: 20260306_0082
Revises: 20260306_0081
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20260306_0082"
down_revision: str | None = "20260306_0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("signal_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("topic", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=True),
        sa.Column("entity_id", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("causation_id", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signals_signal_id", "signals", ["signal_id"], unique=True)
    op.create_index("ix_signals_organization_id", "signals", ["organization_id"], unique=False)
    op.create_index("ix_signals_workspace_id", "signals", ["workspace_id"], unique=False)
    op.create_index("ix_signals_actor_user_id", "signals", ["actor_user_id"], unique=False)
    op.create_index("ix_signals_topic", "signals", ["topic"], unique=False)
    op.create_index("ix_signals_category", "signals", ["category"], unique=False)
    op.create_index("ix_signals_source", "signals", ["source"], unique=False)
    op.create_index("ix_signals_entity_type", "signals", ["entity_type"], unique=False)
    op.create_index("ix_signals_entity_id", "signals", ["entity_id"], unique=False)
    op.create_index("ix_signals_correlation_id", "signals", ["correlation_id"], unique=False)
    op.create_index("ix_signals_causation_id", "signals", ["causation_id"], unique=False)
    op.create_index("ix_signals_request_id", "signals", ["request_id"], unique=False)
    op.create_index("ix_signals_occurred_at", "signals", ["occurred_at"], unique=False)
    op.create_index("ix_signals_created_at", "signals", ["created_at"], unique=False)
    op.create_index(
        "ix_signals_org_occurred_at",
        "signals",
        ["organization_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_signals_org_topic_occurred_at",
        "signals",
        ["organization_id", "topic", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_signals_org_entity_occurred_at",
        "signals",
        ["organization_id", "entity_type", "entity_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_signals_correlation_occurred_at",
        "signals",
        ["correlation_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_signals_causation_occurred_at",
        "signals",
        ["causation_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_signals_causation_occurred_at", table_name="signals")
    op.drop_index("ix_signals_correlation_occurred_at", table_name="signals")
    op.drop_index("ix_signals_org_entity_occurred_at", table_name="signals")
    op.drop_index("ix_signals_org_topic_occurred_at", table_name="signals")
    op.drop_index("ix_signals_org_occurred_at", table_name="signals")
    op.drop_index("ix_signals_created_at", table_name="signals")
    op.drop_index("ix_signals_occurred_at", table_name="signals")
    op.drop_index("ix_signals_request_id", table_name="signals")
    op.drop_index("ix_signals_causation_id", table_name="signals")
    op.drop_index("ix_signals_correlation_id", table_name="signals")
    op.drop_index("ix_signals_entity_id", table_name="signals")
    op.drop_index("ix_signals_entity_type", table_name="signals")
    op.drop_index("ix_signals_source", table_name="signals")
    op.drop_index("ix_signals_category", table_name="signals")
    op.drop_index("ix_signals_topic", table_name="signals")
    op.drop_index("ix_signals_actor_user_id", table_name="signals")
    op.drop_index("ix_signals_workspace_id", table_name="signals")
    op.drop_index("ix_signals_organization_id", table_name="signals")
    op.drop_index("ix_signals_signal_id", table_name="signals")
    op.drop_table("signals")
