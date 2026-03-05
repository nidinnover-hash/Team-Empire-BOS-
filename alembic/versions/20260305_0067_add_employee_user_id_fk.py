"""Add user_id FK to employees table.

Revision ID: 20260305_0067
Revises: 20260302_0066
Create Date: 2026-03-05
"""
import sqlalchemy as sa

from alembic import op

revision = "20260305_0067"
down_revision = "20260302_0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("employees")}
    indexes = {idx["name"] for idx in inspector.get_indexes("employees")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("employees")}

    if "user_id" not in columns:
        op.add_column("employees", sa.Column("user_id", sa.Integer(), nullable=True))
    if "ix_employees_user_id" not in indexes:
        op.create_index("ix_employees_user_id", "employees", ["user_id"], unique=True)
    if "fk_employees_user_id" not in foreign_keys:
        with op.batch_alter_table("employees") as batch_op:
            batch_op.create_foreign_key(
                "fk_employees_user_id",
                "users",
                ["user_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("employees")}
    indexes = {idx["name"] for idx in inspector.get_indexes("employees")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("employees")}

    if "fk_employees_user_id" in foreign_keys:
        with op.batch_alter_table("employees") as batch_op:
            batch_op.drop_constraint("fk_employees_user_id", type_="foreignkey")
    if "ix_employees_user_id" in indexes:
        op.drop_index("ix_employees_user_id", table_name="employees")
    if "user_id" in columns:
        op.drop_column("employees", "user_id")
