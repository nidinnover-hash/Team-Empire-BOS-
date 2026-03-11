"""Add decision_cards table.

Revision ID: 20260305_0073
Revises: 20260305_0072
"""
import sqlalchemy as sa
from alembic import op

revision = "20260305_0073"
down_revision = "20260305_0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "decision_cards" not in tables:
        op.create_table(
            "decision_cards",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("workspace_id", sa.Integer, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("context_summary", sa.Text, nullable=False),
            sa.Column("options_json", sa.Text, nullable=False, server_default="[]"),
            sa.Column("recommendation", sa.String(200), nullable=True),
            sa.Column("category", sa.String(50), nullable=False, server_default="general"),
            sa.Column("urgency", sa.String(20), nullable=False, server_default="normal"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("chosen_option", sa.String(200), nullable=True),
            sa.Column("decision_rationale", sa.Text, nullable=True),
            sa.Column("decided_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("proposed_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("source_type", sa.String(50), nullable=True),
            sa.Column("source_id", sa.String(100), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("decision_cards")
