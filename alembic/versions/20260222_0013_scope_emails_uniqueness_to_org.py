"""scope emails uniqueness to organization

Revision ID: 20260222_0013
Revises: 20260222_0012
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260222_0013"
down_revision = "20260222_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "emails" not in inspector.get_table_names():
        return

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("emails", schema=None) as batch_op:
            batch_op.drop_constraint("uq_emails_gmail_id", type_="unique")
            batch_op.create_unique_constraint(
                "uq_emails_org_gmail_id",
                ["organization_id", "gmail_id"],
            )
        return

    op.drop_constraint("uq_emails_gmail_id", "emails", type_="unique")
    op.create_unique_constraint(
        "uq_emails_org_gmail_id",
        "emails",
        ["organization_id", "gmail_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "emails" not in inspector.get_table_names():
        return

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("emails", schema=None) as batch_op:
            batch_op.drop_constraint("uq_emails_org_gmail_id", type_="unique")
            batch_op.create_unique_constraint("uq_emails_gmail_id", ["gmail_id"])
        return

    op.drop_constraint("uq_emails_org_gmail_id", "emails", type_="unique")
    op.create_unique_constraint("uq_emails_gmail_id", "emails", ["gmail_id"])
