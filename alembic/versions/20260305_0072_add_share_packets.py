"""Add share_packets table.

Revision ID: 20260305_0072
Revises: 20260305_0071
"""
import sqlalchemy as sa
from alembic import op

revision = "20260305_0072"
down_revision = "20260305_0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "share_packets" not in tables:
        op.create_table(
            "share_packets",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("source_workspace_id", sa.Integer, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("target_workspace_id", sa.Integer, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("content_type", sa.String(50), nullable=False, server_default="memory"),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("payload", sa.Text, nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
            sa.Column("proposed_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decided_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decision_note", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("share_packets")
