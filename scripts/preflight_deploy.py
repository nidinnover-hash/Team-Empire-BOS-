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

_REQUIRED_PYTHON_VERSION = (3, 12)


def _current_python_version() -> tuple[int, int]:
    info = sys.version_info
    major = getattr(info, "major", info[0])
    minor = getattr(info, "minor", info[1])
    return (int(major), int(minor))


def _check_python_runtime() -> list[str]:
    current = _current_python_version()
    if current == _REQUIRED_PYTHON_VERSION:
        return []
    return [
        "Python runtime mismatch for deploy preflight "
        f"(required {_REQUIRED_PYTHON_VERSION[0]}.{_REQUIRED_PYTHON_VERSION[1]}, "
        f"detected {current[0]}.{current[1]})"
    ]


def _check_required_env_vars() -> list[str]:
    missing: list[str] = []
    required = [
        "DATABASE_URL",
        "SECRET_KEY",
        "ADMIN_EMAIL",
        "ADMIN_PASSWORD",
        "TOKEN_ENCRYPTION_KEY",
        "OAUTH_STATE_KEY",
    ]
    for key in required:
        value = os.environ.get(key)
        if value is None or not value.strip():
            missing.append(key)
    return missing


def _check_env_quality(*, skip_db: bool = False) -> list[str]:
    issues: list[str] = []
    weak_values = {"", "change_me_in_env", "secret", "changeme", "your_32_plus_char_secret_here"}

    secret_key = (os.environ.get("SECRET_KEY") or "").strip()
    token_key = (os.environ.get("TOKEN_ENCRYPTION_KEY") or "").strip()
    oauth_state_key = (os.environ.get("OAUTH_STATE_KEY") or "").strip()
    admin_password = (os.environ.get("ADMIN_PASSWORD") or "").strip()
    database_url = (os.environ.get("DATABASE_URL") or "").strip().lower()

    if secret_key in weak_values or len(secret_key) < 32:
        issues.append("SECRET_KEY is weak/placeholder (must be random, 32+ chars)")
    if token_key in weak_values or len(token_key) < 32:
        issues.append("TOKEN_ENCRYPTION_KEY is weak/placeholder (must be random, 32+ chars)")
    if oauth_state_key in weak_values or len(oauth_state_key) < 32:
        issues.append("OAUTH_STATE_KEY is weak/placeholder (must be random, 32+ chars)")
    if secret_key and token_key and secret_key == token_key:
        issues.append("TOKEN_ENCRYPTION_KEY must differ from SECRET_KEY")
    if oauth_state_key and oauth_state_key == secret_key:
        issues.append("OAUTH_STATE_KEY must differ from SECRET_KEY")
    if oauth_state_key and oauth_state_key == token_key:
        issues.append("OAUTH_STATE_KEY must differ from TOKEN_ENCRYPTION_KEY")
    if admin_password in {"", "demo", "password", "admin", "123456", "changeme"} or len(admin_password) < 12:
        issues.append("ADMIN_PASSWORD is weak/too short (must be 12+ chars)")
    if database_url.startswith("sqlite") and not skip_db:
        issues.append("DATABASE_URL must point to PostgreSQL for release preflight")

    return issues


def _check_git_hygiene() -> list[str]:
    """Ensure local secret files are not tracked by git."""
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".env"],
        check=False,
        capture_output=True,
        text=True,
    )
    return [".env is tracked by git; remove it from version control and rotate exposed secrets"] if proc.returncode == 0 else []


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

    runtime_issues = _check_python_runtime()
    if runtime_issues:
        print("Preflight failed: unsupported Python runtime:")
        for issue in runtime_issues:
            print(f"- {issue}")
        return 1

    missing = _check_required_env_vars()
    if missing:
        print("Preflight failed: missing required environment variables:")
        for key in missing:
            print(f"- {key}")
        return 1
    quality_issues = _check_env_quality(skip_db=args.skip_db)
    if quality_issues:
        print("Preflight failed: insecure environment values:")
        for issue in quality_issues:
            print(f"- {issue}")
        return 1
    if args.skip_db and (os.environ.get("DATABASE_URL") or "").strip().lower().startswith("sqlite"):
        print(
            "Preflight warning: sqlite DATABASE_URL accepted because --skip-db was used. "
            "Release deploy still requires PostgreSQL.",
        )
    git_hygiene_issues = _check_git_hygiene()
    if git_hygiene_issues:
        print("Preflight failed: repository secret hygiene issues:")
        for issue in git_hygiene_issues:
            print(f"- {issue}")
        return 1

    smoke_cmd = [sys.executable, str(ROOT / "scripts" / "smoke_prod_config.py"), "--import-app"]
    if args.skip_db:
        smoke_cmd.append("--allow-sqlite")
    _run_subprocess(smoke_cmd, "production startup smoke")

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
