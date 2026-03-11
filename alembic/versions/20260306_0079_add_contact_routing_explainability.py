"""add routing explainability fields to contacts

Revision ID: 20260306_0079
Revises: 20260306_0078
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260306_0079"
down_revision: str | None = "20260306_0078"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("contacts")}

    if "routing_source" not in existing:
        op.add_column("contacts", sa.Column("routing_source", sa.String(length=30), nullable=True))
    if "routing_rule_id" not in existing:
        op.add_column("contacts", sa.Column("routing_rule_id", sa.Integer(), nullable=True))

    existing_idxs = {i["name"] for i in inspector.get_indexes("contacts")}
    if op.f("ix_contacts_routing_source") not in existing_idxs:
        op.create_index(op.f("ix_contacts_routing_source"), "contacts", ["routing_source"], unique=False)
    if op.f("ix_contacts_routing_rule_id") not in existing_idxs:
        op.create_index(op.f("ix_contacts_routing_rule_id"), "contacts", ["routing_rule_id"], unique=False)

    try:
        op.create_foreign_key(
            "fk_contacts_routing_rule_id_lead_routing_rules",
            "contacts",
            "lead_routing_rules",
            ["routing_rule_id"],
            ["id"],
            ondelete="SET NULL",
        )
    except Exception:
        pass

    try:
        op.create_check_constraint(
            "ck_contact_routing_source",
            "contacts",
            "routing_source IS NULL OR routing_source IN ('default', 'manual', 'rule', 'fallback')",
        )
    except Exception:
        pass


def downgrade() -> None:
    op.drop_constraint("ck_contact_routing_source", "contacts", type_="check")
    op.drop_constraint("fk_contacts_routing_rule_id_lead_routing_rules", "contacts", type_="foreignkey")
    op.drop_index(op.f("ix_contacts_routing_rule_id"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_routing_source"), table_name="contacts")
    op.drop_column("contacts", "routing_rule_id")
    op.drop_column("contacts", "routing_source")
