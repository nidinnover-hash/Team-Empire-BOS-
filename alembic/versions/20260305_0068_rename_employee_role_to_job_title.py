"""Rename employees.role to employees.job_title.

Revision ID: 20260305_0068
Revises: 20260305_0067
Create Date: 2026-03-05
"""
from alembic import op

revision = "20260305_0068"
down_revision = "20260305_0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("employees", "role", new_column_name="job_title")


def downgrade() -> None:
    op.alter_column("employees", "job_title", new_column_name="role")
