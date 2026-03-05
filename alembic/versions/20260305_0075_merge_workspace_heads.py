"""merge heads after memory embeddings and users super-admin migrations

Revision ID: 20260305_0075
Revises: 20260305_0074, 20260305_0072_users_super_admin
"""

from collections.abc import Sequence


revision: str = "20260305_0075"
down_revision: Sequence[str] | None = ("20260305_0074", "20260305_0072_users_super_admin")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Merge migration only; no schema operations.
    pass


def downgrade() -> None:
    # Merge migration only; no schema operations.
    pass
