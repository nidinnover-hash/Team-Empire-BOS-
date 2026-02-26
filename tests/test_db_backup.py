"""Tests for app/services/db_backup.py — DB backup service."""
from pathlib import Path
from unittest.mock import patch

from app.services import db_backup


async def test_list_backups_empty():
    with patch.object(db_backup, "BACKUP_DIR", Path("/nonexistent/path")):
        result = db_backup.list_backups()
    assert result == []


async def test_list_backups_returns_files(tmp_path):
    (tmp_path / "sqlite_20260226_120000.db").write_bytes(b"test")
    (tmp_path / "sqlite_20260225_120000.db").write_bytes(b"test2")

    with patch.object(db_backup, "BACKUP_DIR", tmp_path):
        result = db_backup.list_backups()

    assert len(result) == 2
    assert all("file" in r and "size_mb" in r for r in result)


async def test_rotate_old_backups(tmp_path):
    for i in range(35):
        (tmp_path / f"sqlite_{i:04d}.db").write_bytes(b"x")

    with patch.object(db_backup, "BACKUP_DIR", tmp_path), \
         patch.object(db_backup, "MAX_BACKUPS", 5):
        removed = db_backup._rotate_old_backups("sqlite")

    assert removed == 30
    assert len(list(tmp_path.glob("sqlite_*"))) == 5


async def test_sqlite_backup_creates_file(tmp_path):
    fake_db = tmp_path / "test.db"
    fake_db.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    backup_dir = tmp_path / "backups"

    with patch.object(db_backup, "_db_is_sqlite", return_value=True), \
         patch.object(db_backup, "_sqlite_path", return_value=fake_db), \
         patch.object(db_backup, "BACKUP_DIR", backup_dir):
        result = await db_backup.create_backup()

    assert result["ok"] is True
    assert result["engine"] == "sqlite"
    assert result["size_mb"] >= 0
    assert backup_dir.exists()


async def test_sqlite_backup_missing_file():
    with patch.object(db_backup, "_db_is_sqlite", return_value=True), \
         patch.object(db_backup, "_sqlite_path", return_value=None), \
         patch.object(db_backup, "BACKUP_DIR", Path("/tmp/test_backup")):
        result = await db_backup.create_backup()

    assert result["ok"] is False
    assert "not found" in result["error"]


async def test_postgres_backup_empty_url():
    with patch.object(db_backup, "_db_is_sqlite", return_value=False), \
         patch.object(db_backup.settings, "DATABASE_URL", ""), \
         patch.object(db_backup, "BACKUP_DIR", Path("/tmp/test_backup")):
        result = await db_backup.create_backup()

    assert result["ok"] is False
    assert "not configured" in result["error"]


async def test_postgres_backup_pg_dump_not_found(tmp_path):
    with patch.object(db_backup, "_db_is_sqlite", return_value=False), \
         patch.object(db_backup.settings, "DATABASE_URL", "postgresql://localhost/testdb"), \
         patch.object(db_backup, "BACKUP_DIR", tmp_path), \
         patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        result = await db_backup.create_backup()

    assert result["ok"] is False
    assert "pg_dump" in result["error"]


async def test_normalize_pg_dump_url_strips_sqlalchemy_driver_suffix():
    assert db_backup._normalize_pg_dump_url("postgresql+asyncpg://user:pw@localhost/db") == "postgresql://user:pw@localhost/db"
    assert db_backup._normalize_pg_dump_url("postgresql+psycopg://user:pw@localhost/db") == "postgresql://user:pw@localhost/db"
    assert db_backup._normalize_pg_dump_url("postgresql://user:pw@localhost/db") == "postgresql://user:pw@localhost/db"


async def test_db_is_sqlite():
    with patch.object(db_backup.settings, "DATABASE_URL", "sqlite+aiosqlite:///test.db"):
        assert db_backup._db_is_sqlite() is True
    with patch.object(db_backup.settings, "DATABASE_URL", "postgresql://localhost/db"):
        assert db_backup._db_is_sqlite() is False
