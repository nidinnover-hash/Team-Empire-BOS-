from __future__ import annotations

import os

import pytest

from scripts import preflight_deploy


@pytest.mark.parametrize(
    ("missing_key",),
    [
        ("DATABASE_URL",),
        ("SECRET_KEY",),
        ("ADMIN_EMAIL",),
        ("ADMIN_PASSWORD",),
        ("TOKEN_ENCRYPTION_KEY",),
    ],
)
def test_check_required_env_vars_reports_missing(monkeypatch: pytest.MonkeyPatch, missing_key: str):
    base_env = {
        "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/test",
        "SECRET_KEY": "0123456789abcdef0123456789abcdef",
        "ADMIN_EMAIL": "owner@example.com",
        "ADMIN_PASSWORD": "StrongPassword123!",
        "TOKEN_ENCRYPTION_KEY": "abcdef0123456789abcdef0123456789",
    }
    for key, value in base_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(missing_key, raising=False)

    missing = preflight_deploy._check_required_env_vars()
    assert missing_key in missing


def test_main_runs_expected_subprocesses_with_skip_db(monkeypatch: pytest.MonkeyPatch):
    for key, value in {
        "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/test",
        "SECRET_KEY": "0123456789abcdef0123456789abcdef",
        "ADMIN_EMAIL": "owner@example.com",
        "ADMIN_PASSWORD": "StrongPassword123!",
        "TOKEN_ENCRYPTION_KEY": "abcdef0123456789abcdef0123456789",
    }.items():
        monkeypatch.setenv(key, value)

    calls: list[tuple[str, list[str]]] = []

    def fake_run_subprocess(cmd: list[str], label: str) -> None:
        calls.append((label, cmd))

    monkeypatch.setattr(preflight_deploy, "_run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(preflight_deploy, "_check_db_connectivity", lambda: None)
    monkeypatch.setattr(preflight_deploy, "_check_git_hygiene", lambda: [])
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.setenv("PYTHONUTF8", "1")
    monkeypatch.setattr("sys.argv", ["preflight_deploy.py", "--skip-db"])

    assert preflight_deploy.main() == 0
    assert [label for label, _ in calls] == [
        "production startup smoke",
        "migration heads",
    ]


def test_check_env_quality_flags_weak_values(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./local.db")
    monkeypatch.setenv("SECRET_KEY", "short")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "short")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin")

    issues = preflight_deploy._check_env_quality()
    assert any("SECRET_KEY" in issue for issue in issues)
    assert any("TOKEN_ENCRYPTION_KEY" in issue for issue in issues)
    assert any("ADMIN_PASSWORD" in issue for issue in issues)
    assert any("DATABASE_URL" in issue for issue in issues)


def test_main_fails_when_dotenv_is_tracked(monkeypatch: pytest.MonkeyPatch):
    for key, value in {
        "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/test",
        "SECRET_KEY": "0123456789abcdef0123456789abcdef",
        "ADMIN_EMAIL": "owner@example.com",
        "ADMIN_PASSWORD": "StrongPassword123!",
        "TOKEN_ENCRYPTION_KEY": "abcdef0123456789abcdef0123456789",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(preflight_deploy, "_check_git_hygiene", lambda: [".env is tracked by git"])
    monkeypatch.setattr("sys.argv", ["preflight_deploy.py", "--skip-db"])

    assert preflight_deploy.main() == 1
