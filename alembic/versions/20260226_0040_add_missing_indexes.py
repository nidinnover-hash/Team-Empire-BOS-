"""Add missing indexes on approved_by and created_by FK columns.

Revision ID: 20260226_0040
Revises: 20260226_0039
Create Date: 2026-02-26
"""
import sqlalchemy as sa
from alembic import op

revision = "20260226_0040"
down_revision = "20260226_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_dtp = {i["name"] for i in inspector.get_indexes("daily_task_plans")}
    if "ix_daily_task_plans_approved_by" not in existing_dtp:
        op.create_index("ix_daily_task_plans_approved_by", "daily_task_plans", ["approved_by"])

    existing_dl = {i["name"] for i in inspector.get_indexes("decision_logs")}
    if "ix_decision_logs_created_by" not in existing_dl:
        op.create_index("ix_decision_logs_created_by", "decision_logs", ["created_by"])

    existing_sp = {i["name"] for i in inspector.get_indexes("social_posts")}
    if "ix_social_posts_created_by_user_id" not in existing_sp:
        op.create_index("ix_social_posts_created_by_user_id", "social_posts", ["created_by_user_id"])
    if "ix_social_posts_approved_by_user_id" not in existing_sp:
        op.create_index("ix_social_posts_approved_by_user_id", "social_posts", ["approved_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_social_posts_approved_by_user_id", "social_posts")
    op.drop_index("ix_social_posts_created_by_user_id", "social_posts")
    op.drop_index("ix_decision_logs_created_by", "decision_logs")
    op.drop_index("ix_daily_task_plans_approved_by", "daily_task_plans")
