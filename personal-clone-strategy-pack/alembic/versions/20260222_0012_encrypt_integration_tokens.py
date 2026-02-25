"""encrypt existing integration tokens at rest

Revision ID: 20260222_0012
Revises: 20260222_0011
Create Date: 2026-02-22

Data migration: re-encrypts any plaintext access_token / refresh_token values
already stored in integrations.config_json using the app's token_crypto module.

IMPORTANT: This migration reads SECRET_KEY from settings. It must be run with
the same SECRET_KEY that the application uses. If tokens are already encrypted
(e.g. running twice), decrypt_config silently skips them.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260222_0012"
down_revision = "20260222_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Only run if there are any integrations to migrate
    rows = bind.execute(sa.text("SELECT id, config_json FROM integrations")).fetchall()
    if not rows:
        return

    from app.core.token_crypto import encrypt_config, decrypt_config
    import json

    for row in rows:
        row_id = row[0]
        config = row[1]
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except Exception:
                continue
        if not config:
            continue

        # decrypt_config gracefully handles already-plaintext values.
        # Then re-encrypt cleanly.
        plaintext = decrypt_config(config)
        encrypted = encrypt_config(plaintext)

        bind.execute(
            sa.text("UPDATE integrations SET config_json = :cfg WHERE id = :id"),
            {"cfg": json.dumps(encrypted), "id": row_id},
        )


def downgrade() -> None:
    # Intentionally not decrypting on downgrade — doing so would expose tokens
    # in a migration file's output. If you need to rollback, rotate the tokens.
    pass
