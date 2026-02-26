"""Add missing indexes on approved_by and created_by FK columns.

Revision ID: 20260226_0040
Revises: 20260226_0039
Create Date: 2026-02-26
"""
from alembic import op

revision = "20260226_0040"
down_revision = "20260226_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_daily_task_plans_approved_by", "daily_task_plans", ["approved_by"])
    op.create_index("ix_decision_logs_created_by", "decision_logs", ["created_by"])
    op.create_index("ix_social_posts_created_by_user_id", "social_posts", ["created_by_user_id"])
    op.create_index("ix_social_posts_approved_by_user_id", "social_posts", ["approved_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_social_posts_approved_by_user_id", "social_posts")
    op.drop_index("ix_social_posts_created_by_user_id", "social_posts")
    op.drop_index("ix_decision_logs_created_by", "decision_logs")
    op.drop_index("ix_daily_task_plans_approved_by", "daily_task_plans")
