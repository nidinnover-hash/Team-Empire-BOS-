"""add decision traces table

Revision ID: 20260223_0014
Revises: 20260222_0013
Create Date: 2026-02-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260223_0014"
down_revision = "20260222_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "decision_traces" in inspector.get_table_names():
        return

    op.create_table(
        "decision_traces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("trace_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("signals_json", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("daily_run_id", sa.Integer(), nullable=True),
        sa.Column("source_event_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_traces_organization_id", "decision_traces", ["organization_id"], unique=False)
    op.create_index("ix_decision_traces_trace_type", "decision_traces", ["trace_type"], unique=False)
    op.create_index("ix_decision_traces_actor_user_id", "decision_traces", ["actor_user_id"], unique=False)
    op.create_index("ix_decision_traces_daily_run_id", "decision_traces", ["daily_run_id"], unique=False)
    op.create_index("ix_decision_traces_source_event_id", "decision_traces", ["source_event_id"], unique=False)
    op.create_index("ix_decision_traces_created_at", "decision_traces", ["created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "decision_traces" not in inspector.get_table_names():
        return

    op.drop_index("ix_decision_traces_created_at", table_name="decision_traces")
    op.drop_index("ix_decision_traces_source_event_id", table_name="decision_traces")
    op.drop_index("ix_decision_traces_daily_run_id", table_name="decision_traces")
    op.drop_index("ix_decision_traces_actor_user_id", table_name="decision_traces")
    op.drop_index("ix_decision_traces_trace_type", table_name="decision_traces")
    op.drop_index("ix_decision_traces_organization_id", table_name="decision_traces")
    op.drop_table("decision_traces")
