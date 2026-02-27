from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings


def _check_required_env_vars() -> list[str]:
    missing: list[str] = []
    required = [
        "DATABASE_URL",
        "SECRET_KEY",
        "ADMIN_EMAIL",
        "ADMIN_PASSWORD",
        "TOKEN_ENCRYPTION_KEY",
    ]
    for key in required:
        value = os.environ.get(key)
        if value is None or not value.strip():
            missing.append(key)
    return missing


def _run_subprocess(cmd: list[str], label: str) -> None:
    print(f"[preflight] {label}: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


async def _check_db_connectivity() -> None:
    print("[preflight] DB connectivity: SELECT 1")
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        connect_args={"timeout": 10} if settings.DATABASE_URL.startswith("sqlite") else {},
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deployment preflight checks.")
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip DB connectivity check.",
    )
    args = parser.parse_args()

    missing = _check_required_env_vars()
    if missing:
        print("Preflight failed: missing required environment variables:")
        for key in missing:
            print(f"- {key}")
        return 1

    _run_subprocess(
        [sys.executable, str(ROOT / "scripts" / "smoke_prod_config.py"), "--import-app"],
        "production startup smoke",
    )

    if not args.skip_db:
        try:
            asyncio.run(_check_db_connectivity())
        except Exception as exc:
            print(f"Preflight failed: database connectivity check failed: {type(exc).__name__}: {exc}")
            return 1

    _run_subprocess(
        [sys.executable, str(ROOT / "scripts" / "check_migration_heads.py")],
        "migration heads",
    )

    print("Preflight checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
