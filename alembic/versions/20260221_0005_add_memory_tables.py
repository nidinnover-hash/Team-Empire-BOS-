"""add memory tables

Revision ID: 20260221_0005
Revises: 20260221_0004
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260221_0005"
down_revision = "20260221_0004"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(i.get("name") == index_name for i in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()

    # profile_memory — stores identity/rules/goals/preferences
    if not _table_exists("profile_memory"):
        op.create_table(
            "profile_memory",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("key", sa.String(length=100), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("category", sa.String(length=50), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("key", name="uq_profile_memory_key"),
        )
    if not _index_exists("profile_memory", "ix_profile_memory_category"):
        op.create_index("ix_profile_memory_category", "profile_memory", ["category"], unique=False)

    # team_members
    if not _table_exists("team_members"):
        op.create_table(
            "team_members",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("role_title", sa.String(length=100), nullable=True),
            sa.Column("team", sa.String(length=50), nullable=True),
            sa.Column("reports_to_id", sa.Integer(), nullable=True),
            sa.Column("skills", sa.Text(), nullable=True),
            sa.Column("ai_level", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("current_project", sa.String(length=200), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not _index_exists("team_members", "ix_team_members_team"):
        op.create_index("ix_team_members_team", "team_members", ["team"], unique=False)
    if not _index_exists("team_members", "ix_team_members_is_active"):
        op.create_index("ix_team_members_is_active", "team_members", ["is_active"], unique=False)

    # self-referential FK, skip on SQLite
    if bind.dialect.name != "sqlite":
        inspector = sa.inspect(bind)
        fks = {fk.get("name") for fk in inspector.get_foreign_keys("team_members")}
        if "fk_team_members_reports_to" not in fks:
            op.create_foreign_key(
                "fk_team_members_reports_to",
                "team_members", "team_members",
                ["reports_to_id"], ["id"],
                ondelete="SET NULL",
            )

    # daily_context
    if not _table_exists("daily_context"):
        op.create_table(
            "daily_context",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("context_type", sa.String(length=50), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("related_to", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not _index_exists("daily_context", "ix_daily_context_date"):
        op.create_index("ix_daily_context_date", "daily_context", ["date"], unique=False)
    if not _index_exists("daily_context", "ix_daily_context_type"):
        op.create_index("ix_daily_context_type", "daily_context", ["context_type"], unique=False)


def downgrade() -> None:
    if _index_exists("daily_context", "ix_daily_context_type"):
        op.drop_index("ix_daily_context_type", table_name="daily_context")
    if _index_exists("daily_context", "ix_daily_context_date"):
        op.drop_index("ix_daily_context_date", table_name="daily_context")
    if _table_exists("daily_context"):
        op.drop_table("daily_context")

    if _table_exists("team_members"):
        bind = op.get_bind()
        if bind.dialect.name != "sqlite":
            inspector = sa.inspect(bind)
            fks = {fk.get("name") for fk in inspector.get_foreign_keys("team_members")}
            if "fk_team_members_reports_to" in fks:
                op.drop_constraint("fk_team_members_reports_to", "team_members", type_="foreignkey")
    if _index_exists("team_members", "ix_team_members_is_active"):
        op.drop_index("ix_team_members_is_active", table_name="team_members")
    if _index_exists("team_members", "ix_team_members_team"):
        op.drop_index("ix_team_members_team", table_name="team_members")
    if _table_exists("team_members"):
        op.drop_table("team_members")

    if _index_exists("profile_memory", "ix_profile_memory_category"):
        op.drop_index("ix_profile_memory_category", table_name="profile_memory")
    if _table_exists("profile_memory"):
        op.drop_table("profile_memory")
