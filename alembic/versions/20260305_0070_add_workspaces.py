"""add workspaces, workspace_memberships, and workspace_id FK on memory tables

Revision ID: 20260305_0070
Revises: 20260305_0069
"""
import sqlalchemy as sa

from alembic import op

revision = "20260305_0070"
down_revision = "20260305_0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- workspaces ---
    if not inspector.has_table("workspaces"):
        op.create_table(
            "workspaces",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("slug", sa.String(120), nullable=False),
            sa.Column("workspace_type", sa.String(30), nullable=False, server_default="general"),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("config_json", sa.Text, nullable=False, server_default="{}"),
            sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "slug", name="uq_workspace_org_slug"),
        )
    workspace_indexes = {idx["name"] for idx in inspector.get_indexes("workspaces")}
    if "ix_workspaces_organization_id" not in workspace_indexes:
        op.create_index("ix_workspaces_organization_id", "workspaces", ["organization_id"])
    if "ix_workspaces_is_default" not in workspace_indexes:
        op.create_index("ix_workspaces_is_default", "workspaces", ["is_default"])
    if "ix_workspaces_is_active" not in workspace_indexes:
        op.create_index("ix_workspaces_is_active", "workspaces", ["is_active"])

    # --- workspace_memberships ---
    if not inspector.has_table("workspace_memberships"):
        op.create_table(
            "workspace_memberships",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("workspace_id", sa.Integer, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role_override", sa.String(30), nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_membership"),
        )
    membership_indexes = {idx["name"] for idx in inspector.get_indexes("workspace_memberships")}
    if "ix_workspace_memberships_workspace_id" not in membership_indexes:
        op.create_index("ix_workspace_memberships_workspace_id", "workspace_memberships", ["workspace_id"])
    if "ix_workspace_memberships_user_id" not in membership_indexes:
        op.create_index("ix_workspace_memberships_user_id", "workspace_memberships", ["user_id"])

    # --- nullable workspace_id FK on memory tables ---
    for table in ("profile_memory", "daily_context", "avatar_memory", "clone_memory_entries", "tasks"):
        if not inspector.has_table(table):
            continue
        columns = {col["name"] for col in inspector.get_columns(table)}
        indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys(table)}
        fk_name = f"fk_{table}_workspace_id"
        if "workspace_id" not in columns:
            op.add_column(table, sa.Column("workspace_id", sa.Integer, nullable=True))
        if f"ix_{table}_workspace_id" not in indexes:
            op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])
        if fk_name not in foreign_keys:
            with op.batch_alter_table(table) as batch_op:
                batch_op.create_foreign_key(
                    fk_name,
                    "workspaces",
                    ["workspace_id"],
                    ["id"],
                    ondelete="SET NULL",
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in ("tasks", "clone_memory_entries", "avatar_memory", "daily_context", "profile_memory"):
        if not inspector.has_table(table):
            continue
        columns = {col["name"] for col in inspector.get_columns(table)}
        indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys(table)}
        fk_name = f"fk_{table}_workspace_id"
        if fk_name in foreign_keys:
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_constraint(fk_name, type_="foreignkey")
        if f"ix_{table}_workspace_id" in indexes:
            op.drop_index(f"ix_{table}_workspace_id", table_name=table)
        if "workspace_id" in columns:
            op.drop_column(table, "workspace_id")

    if inspector.has_table("workspace_memberships"):
        membership_indexes = {idx["name"] for idx in inspector.get_indexes("workspace_memberships")}
        if "ix_workspace_memberships_user_id" in membership_indexes:
            op.drop_index("ix_workspace_memberships_user_id", table_name="workspace_memberships")
        if "ix_workspace_memberships_workspace_id" in membership_indexes:
            op.drop_index("ix_workspace_memberships_workspace_id", table_name="workspace_memberships")
        op.drop_table("workspace_memberships")

    if inspector.has_table("workspaces"):
        workspace_indexes = {idx["name"] for idx in inspector.get_indexes("workspaces")}
        if "ix_workspaces_is_active" in workspace_indexes:
            op.drop_index("ix_workspaces_is_active", table_name="workspaces")
        if "ix_workspaces_is_default" in workspace_indexes:
            op.drop_index("ix_workspaces_is_default", table_name="workspaces")
        if "ix_workspaces_organization_id" in workspace_indexes:
            op.drop_index("ix_workspaces_organization_id", table_name="workspaces")
        op.drop_table("workspaces")
