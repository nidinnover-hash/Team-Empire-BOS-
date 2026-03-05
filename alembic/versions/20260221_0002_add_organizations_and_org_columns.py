"""add organizations and org_id columns

Revision ID: 20260221_0002
Revises: 20260221_0001
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


revision = "20260221_0002"
down_revision = "20260221_0001b"
branch_labels = None
depends_on = None


def _add_org_column(table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
    if "organization_id" in existing_columns:
        return
    op.add_column(
        table_name,
        sa.Column("organization_id", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(f"ix_{table_name}_organization_id", table_name, ["organization_id"], unique=False)
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            f"fk_{table_name}_organization_id_organizations",
            table_name,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def _drop_org_column(table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
    if "organization_id" not in existing_columns:
        return
    if bind.dialect.name != "sqlite":
        op.drop_constraint(f"fk_{table_name}_organization_id_organizations", table_name, type_="foreignkey")
    op.drop_index(f"ix_{table_name}_organization_id", table_name=table_name)
    op.drop_column(table_name, "organization_id")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "organizations" not in table_names:
        op.create_table(
            "organizations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)
        op.create_unique_constraint("uq_organizations_name", "organizations", ["name"])

    existing_default = bind.execute(sa.text("SELECT id FROM organizations WHERE id = 1 LIMIT 1")).fetchone()
    if existing_default is None:
        op.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) VALUES (:id, :name, :slug, :created_at)"
            ).bindparams(
                id=1,
                name="Default Organization",
                slug="default",
                created_at=datetime(2026, 2, 21, tzinfo=timezone.utc),
            )
        )

    for table in [
        "users",
        "events",
        "approvals",
        "commands",
        "notes",
        "projects",
        "tasks",
        "goals",
        "contacts",
        "finance_entries",
    ]:
        _add_org_column(table)


def downgrade() -> None:
    for table in [
        "finance_entries",
        "contacts",
        "goals",
        "tasks",
        "projects",
        "notes",
        "commands",
        "approvals",
        "events",
        "users",
    ]:
        _drop_org_column(table)

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "organizations" in inspector.get_table_names():
        uniques = {c.get("name") for c in inspector.get_unique_constraints("organizations")}
        indexes = {i.get("name") for i in inspector.get_indexes("organizations")}
        if "uq_organizations_name" in uniques:
            op.drop_constraint("uq_organizations_name", "organizations", type_="unique")
        if "ix_organizations_slug" in indexes:
            op.drop_index("ix_organizations_slug", table_name="organizations")
        op.drop_table("organizations")
