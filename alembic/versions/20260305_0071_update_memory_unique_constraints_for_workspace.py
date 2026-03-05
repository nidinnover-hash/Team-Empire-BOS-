"""Update memory unique constraints to include workspace_id.

Revision ID: 20260305_0071
Revises: 20260305_0070
"""
from alembic import op

revision = "20260305_0071"
down_revision = "20260305_0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ProfileMemory: drop old (org_id, key) constraint, add (org_id, key, workspace_id)
    with op.batch_alter_table("profile_memory") as batch_op:
        batch_op.drop_constraint("uq_profile_memory_org_key", type_="unique")
        batch_op.create_unique_constraint(
            "uq_profile_memory_org_key_ws",
            ["organization_id", "key", "workspace_id"],
        )

    # AvatarMemory: drop old (org_id, mode, key) constraint, add (org_id, mode, key, workspace_id)
    with op.batch_alter_table("avatar_memory") as batch_op:
        batch_op.drop_constraint("uq_avatar_memory_org_mode_key", type_="unique")
        batch_op.create_unique_constraint(
            "uq_avatar_memory_org_mode_key_ws",
            ["organization_id", "avatar_mode", "key", "workspace_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("avatar_memory") as batch_op:
        batch_op.drop_constraint("uq_avatar_memory_org_mode_key_ws", type_="unique")
        batch_op.create_unique_constraint(
            "uq_avatar_memory_org_mode_key",
            ["organization_id", "avatar_mode", "key"],
        )

    with op.batch_alter_table("profile_memory") as batch_op:
        batch_op.drop_constraint("uq_profile_memory_org_key_ws", type_="unique")
        batch_op.create_unique_constraint(
            "uq_profile_memory_org_key",
            ["organization_id", "key"],
        )
