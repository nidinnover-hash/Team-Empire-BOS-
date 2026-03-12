from __future__ import annotations

import os
import subprocess
import sys

CHECKS: list[list[str]] = [
    [sys.executable, "scripts/preflight_python.py"],
    [sys.executable, "scripts/check_migration_revisions.py"],
    [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "app",
        "tests",
        "scripts/dev_gate.py",
        "scripts/generate_sdk_clients.py",
        "scripts/check_migration_revisions.py",
    ],
    [sys.executable, "-m", "mypy", "app/services/webhook.py", "app/logs/audit.py"],
    [sys.executable, "scripts/generate_sdk_clients.py"],
    [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_openapi_contracts.py",
        "tests/test_sdk_clients.py",
        "tests/test_sdk_generation_deterministic.py",
        "tests/test_sdk_generation_coverage.py",
        "tests/test_pr_checklist_guard.py",
        "tests/test_sdk_release_notes_check.py",
        "tests/test_architecture_guards.py",
    ],
]


def main() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    for cmd in CHECKS:
        sys.stdout.write(f"\n==> {' '.join(cmd)}\n")
        proc = subprocess.run(cmd, check=False, env=env)
        if proc.returncode != 0:
            return proc.returncode
    sys.stdout.write("\nDeveloper fast gate passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
