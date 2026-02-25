"""add social posts table

Revision ID: 20260224_0029
Revises: 20260224_0028
Create Date: 2026-02-24 23:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260224_0029"
down_revision = "20260224_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "social_posts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("content_mode", sa.String(length=30), nullable=False, server_default="social_media"),
        sa.Column("platform", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("media_url", sa.String(length=1024), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'queued', 'approved', 'published', 'failed')",
            name="ck_social_post_status",
        ),
        sa.CheckConstraint(
            "content_mode IN ('social_media', 'entertainment')",
            name="ck_social_post_content_mode",
        ),
        sa.CheckConstraint(
            "("
            "(content_mode = 'social_media' AND platform IN ('instagram','facebook','linkedin','x','tiktok','other'))"
            " OR "
            "(content_mode = 'entertainment' AND platform IN ('youtube','audible'))"
            ")",
            name="ck_social_post_mode_platform",
        ),
    )
    op.create_index("ix_social_posts_organization_id", "social_posts", ["organization_id"], unique=False)
    op.create_index("ix_social_posts_content_mode", "social_posts", ["content_mode"], unique=False)
    op.create_index("ix_social_posts_platform", "social_posts", ["platform"], unique=False)
    op.create_index("ix_social_posts_status", "social_posts", ["status"], unique=False)
    op.create_index("ix_social_posts_scheduled_for", "social_posts", ["scheduled_for"], unique=False)
    op.create_index("ix_social_posts_published_at", "social_posts", ["published_at"], unique=False)
    op.create_index("ix_social_posts_created_at", "social_posts", ["created_at"], unique=False)
    op.create_index("ix_social_posts_updated_at", "social_posts", ["updated_at"], unique=False)

    op.alter_column("social_posts", "status", server_default=None)
    op.alter_column("social_posts", "content_mode", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_social_posts_updated_at", table_name="social_posts")
    op.drop_index("ix_social_posts_created_at", table_name="social_posts")
    op.drop_index("ix_social_posts_published_at", table_name="social_posts")
    op.drop_index("ix_social_posts_scheduled_for", table_name="social_posts")
    op.drop_index("ix_social_posts_status", table_name="social_posts")
    op.drop_index("ix_social_posts_content_mode", table_name="social_posts")
    op.drop_index("ix_social_posts_platform", table_name="social_posts")
    op.drop_index("ix_social_posts_organization_id", table_name="social_posts")
    op.drop_table("social_posts")
