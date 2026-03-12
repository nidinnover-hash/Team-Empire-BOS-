"""add CRM quote, playbook, and survey tables

Revision ID: 20260310_0086
Revises: 20260309_0085
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260310_0086"
down_revision: str | None = "20260309_0085"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "playbooks" not in tables:
        op.create_table(
            "playbooks",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("deal_stage", sa.String(length=50), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_playbooks_organization_id", "playbooks", ["organization_id"])

    if "quotes" not in tables:
        op.create_table(
            "quotes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("deal_id", sa.Integer(), nullable=True),
            sa.Column("contact_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("subtotal", sa.Numeric(precision=14, scale=2), nullable=False),
            sa.Column("discount_percent", sa.Numeric(precision=5, scale=2), nullable=False),
            sa.Column("tax_percent", sa.Numeric(precision=5, scale=2), nullable=False),
            sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False),
            sa.Column("expiry_date", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_quotes_organization_id", "quotes", ["organization_id"])

    if "survey_definitions" not in tables:
        op.create_table(
            "survey_definitions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("questions_json", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("total_responses", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(
            "ix_survey_definitions_organization_id",
            "survey_definitions",
            ["organization_id"],
        )

    if "playbook_steps" not in tables:
        op.create_table(
            "playbook_steps",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "playbook_id",
                sa.Integer(),
                sa.ForeignKey("playbooks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("step_order", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("is_required", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_playbook_steps_organization_id", "playbook_steps", ["organization_id"])
        op.create_index("ix_playbook_steps_playbook_id", "playbook_steps", ["playbook_id"])

    if "quote_line_items" not in tables:
        op.create_table(
            "quote_line_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "quote_id",
                sa.Integer(),
                sa.ForeignKey("quotes.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("description", sa.String(length=500), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=False),
            sa.Column("discount_percent", sa.Numeric(precision=5, scale=2), nullable=False),
            sa.Column("line_total", sa.Numeric(precision=14, scale=2), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(
            "ix_quote_line_items_organization_id",
            "quote_line_items",
            ["organization_id"],
        )
        op.create_index("ix_quote_line_items_quote_id", "quote_line_items", ["quote_id"])

    if "survey_responses" not in tables:
        op.create_table(
            "survey_responses",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "survey_id",
                sa.Integer(),
                sa.ForeignKey("survey_definitions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("contact_id", sa.Integer(), nullable=True),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("nps_score", sa.Integer(), nullable=True),
            sa.Column("answers_json", sa.Text(), nullable=False),
            sa.Column("feedback", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(
            "ix_survey_responses_organization_id",
            "survey_responses",
            ["organization_id"],
        )
        op.create_index("ix_survey_responses_survey_id", "survey_responses", ["survey_id"])


def downgrade() -> None:
    op.drop_index("ix_survey_responses_survey_id", table_name="survey_responses")
    op.drop_index("ix_survey_responses_organization_id", table_name="survey_responses")
    op.drop_table("survey_responses")

    op.drop_index("ix_quote_line_items_quote_id", table_name="quote_line_items")
    op.drop_index("ix_quote_line_items_organization_id", table_name="quote_line_items")
    op.drop_table("quote_line_items")

    op.drop_index("ix_playbook_steps_playbook_id", table_name="playbook_steps")
    op.drop_index("ix_playbook_steps_organization_id", table_name="playbook_steps")
    op.drop_table("playbook_steps")

    op.drop_index("ix_survey_definitions_organization_id", table_name="survey_definitions")
    op.drop_table("survey_definitions")

    op.drop_index("ix_quotes_organization_id", table_name="quotes")
    op.drop_table("quotes")

    op.drop_index("ix_playbooks_organization_id", table_name="playbooks")
    op.drop_table("playbooks")
