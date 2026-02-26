"""hardening: add FKs on events/executions, index on integrations, drop org_id defaults

Revision ID: 20260226_0035
Revises: 20260225_0034
Create Date: 2026-02-26 12:00:00.000000

Changes applied:
  1. Event.actor_user_id  → FK to users.id (SET NULL)
  2. Execution.triggered_by → FK to users.id (RESTRICT)
  3. Integration.last_sync_at → index
  4. Event.organization_id  → remove server_default=1
  5. AiCallLog.organization_id → remove server_default=1
"""

from alembic import op
import sqlalchemy as sa


revision = "20260226_0035"
down_revision = "20260225_0034"
branch_labels = None
depends_on = None


def _has_constraint(inspector, table: str, name: str) -> bool:
    for fk in inspector.get_foreign_keys(table):
        if fk.get("name") == name:
            return True
    return False


def _has_index(inspector, table: str, name: str) -> bool:
    for idx in inspector.get_indexes(table):
        if idx.get("name") == name:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # 1. Event.actor_user_id FK → users.id (SET NULL)
    if "events" in tables and dialect != "sqlite":
        if not _has_constraint(inspector, "events", "fk_event_actor_user"):
            op.create_foreign_key(
                "fk_event_actor_user",
                "events",
                "users",
                ["actor_user_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # 2. Execution.triggered_by FK → users.id (RESTRICT)
    if "executions" in tables and dialect != "sqlite":
        if not _has_constraint(inspector, "executions", "fk_execution_triggered_by_user"):
            op.create_foreign_key(
                "fk_execution_triggered_by_user",
                "executions",
                "users",
                ["triggered_by"],
                ["id"],
                ondelete="RESTRICT",
            )

    # 3. Integration.last_sync_at index
    if "integrations" in tables:
        if not _has_index(inspector, "integrations", "ix_integrations_last_sync_at"):
            op.create_index(
                "ix_integrations_last_sync_at",
                "integrations",
                ["last_sync_at"],
            )

    # 4. Remove server_default on events.organization_id
    if "events" in tables and dialect != "sqlite":
        op.alter_column(
            "events",
            "organization_id",
            server_default=None,
        )

    # 5. Remove server_default on ai_call_logs.organization_id
    if "ai_call_logs" in tables and dialect != "sqlite":
        op.alter_column(
            "ai_call_logs",
            "organization_id",
            server_default=None,
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Restore server_default=1
    if dialect != "sqlite":
        try:
            op.alter_column("ai_call_logs", "organization_id", server_default=sa.text("1"))
        except Exception:
            pass
        try:
            op.alter_column("events", "organization_id", server_default=sa.text("1"))
        except Exception:
            pass

    # Drop index
    try:
        op.drop_index("ix_integrations_last_sync_at", table_name="integrations")
    except Exception:
        pass

    # Drop FKs
    if dialect != "sqlite":
        try:
            op.drop_constraint("fk_execution_triggered_by_user", "executions", type_="foreignkey")
        except Exception:
            pass
        try:
            op.drop_constraint("fk_event_actor_user", "events", type_="foreignkey")
        except Exception:
            pass
