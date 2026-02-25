"""
Re-encrypt integration token fields with the active TOKEN_ENCRYPTION_KEY.

Usage:
  .venv\\Scripts\\python.exe scripts/repair_integration_tokens.py --apply
  .venv\\Scripts\\python.exe scripts/repair_integration_tokens.py
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.token_crypto import decrypt_config, encrypt_config
from app.db.session import AsyncSessionLocal
from app.models.integration import Integration
from app.models import organization as _model_organization  # noqa: F401


TOKEN_FIELDS = ("access_token", "refresh_token", "api_token")


async def _repair(apply_changes: bool) -> None:
    async with AsyncSessionLocal() as db:
        rows = list((await db.execute(select(Integration))).scalars().all())
        scanned = 0
        repaired = 0
        malformed = 0
        for row in rows:
            scanned += 1
            original = dict(row.config_json or {})
            decrypted = decrypt_config(original)
            # decrypt_config clears malformed encrypted values to ""
            malformed += sum(
                1
                for field in TOKEN_FIELDS
                if isinstance(original.get(field), str)
                and original.get(field, "").startswith("gAAAA")
                and not decrypted.get(field)
            )
            normalized = encrypt_config(decrypted)
            if normalized != original:
                repaired += 1
                if apply_changes:
                    row.config_json = normalized
        if apply_changes and repaired:
            await db.commit()
        print(
            f"scanned={scanned} repaired={repaired} malformed_tokens={malformed} "
            f"mode={'apply' if apply_changes else 'dry-run'}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist repaired token payloads to the database",
    )
    args = parser.parse_args()
    asyncio.run(_repair(apply_changes=args.apply))


if __name__ == "__main__":
    main()
