"""Automated database backup service.

Supports SQLite (file copy) and PostgreSQL (pg_dump via subprocess).
Backups are stored in Data/backups/ with rotation to prevent disk bloat.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

BACKUP_DIR = Path("Data") / "backups"
MAX_BACKUPS = 30  # keep last N backups, delete older ones


def _db_is_sqlite() -> bool:
    return (settings.DATABASE_URL or "").startswith("sqlite")


def _sqlite_path() -> Path | None:
    url = (settings.DATABASE_URL or "").strip()
    if not url.startswith("sqlite"):
        return None
    candidate = url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "").split("?")[0]
    p = Path(candidate).resolve()
    return p if p.exists() else None


def _rotate_old_backups(prefix: str) -> int:
    """Delete oldest backups beyond MAX_BACKUPS. Returns count deleted."""
    if not BACKUP_DIR.exists():
        return 0
    backups = sorted(BACKUP_DIR.glob(f"{prefix}_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for old in backups[MAX_BACKUPS:]:
        old.unlink(missing_ok=True)
        removed += 1
    return removed


async def create_backup() -> dict:
    """Create a database backup. Returns status dict."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    if _db_is_sqlite():
        return await _backup_sqlite(ts)
    return await _backup_postgres(ts)


async def _backup_sqlite(ts: str) -> dict:
    db_path = _sqlite_path()
    if db_path is None:
        return {"ok": False, "error": "SQLite database file not found"}

    backup_name = f"sqlite_{ts}.db"
    backup_path = BACKUP_DIR / backup_name

    try:
        shutil.copy2(str(db_path), str(backup_path))
    except OSError as exc:
        logger.error("SQLite backup failed: %s", exc)
        return {"ok": False, "error": "Backup copy failed"}

    size_mb = round(backup_path.stat().st_size / (1024 * 1024), 2)
    removed = _rotate_old_backups("sqlite")
    logger.info("SQLite backup created: %s (%.2f MB, %d old removed)", backup_name, size_mb, removed)
    return {
        "ok": True,
        "engine": "sqlite",
        "file": backup_name,
        "size_mb": size_mb,
        "rotated": removed,
        "created_at": datetime.now(UTC).isoformat(),
    }


async def _backup_postgres(ts: str) -> dict:
    url = (settings.DATABASE_URL or "").strip()
    if not url:
        return {"ok": False, "error": "DATABASE_URL not configured"}

    backup_name = f"postgres_{ts}.sql.gz"
    backup_path = BACKUP_DIR / backup_name

    # pg_dump piped through gzip
    cmd = f'pg_dump "{url}" | gzip > "{backup_path}"'
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode != 0:
            err_msg = (stderr or b"").decode()[:200]
            logger.error("pg_dump failed (rc=%d): %s", proc.returncode, err_msg)
            backup_path.unlink(missing_ok=True)
            return {"ok": False, "error": "pg_dump failed"}
    except TimeoutError:
        logger.error("pg_dump timed out after 300s")
        backup_path.unlink(missing_ok=True)
        return {"ok": False, "error": "pg_dump timed out"}
    except FileNotFoundError:
        return {"ok": False, "error": "pg_dump not found on PATH"}

    size_mb = round(backup_path.stat().st_size / (1024 * 1024), 2) if backup_path.exists() else 0
    removed = _rotate_old_backups("postgres")
    logger.info("PostgreSQL backup created: %s (%.2f MB, %d old removed)", backup_name, size_mb, removed)
    return {
        "ok": True,
        "engine": "postgres",
        "file": backup_name,
        "size_mb": size_mb,
        "rotated": removed,
        "created_at": datetime.now(UTC).isoformat(),
    }


def list_backups() -> list[dict]:
    """List existing backups, newest first."""
    if not BACKUP_DIR.exists():
        return []
    files = sorted(BACKUP_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "file": f.name,
            "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
            "created_at": datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat(),
        }
        for f in files
        if f.is_file() and not f.name.startswith(".")
    ]
