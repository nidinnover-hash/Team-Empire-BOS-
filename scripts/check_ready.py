from __future__ import annotations

import importlib
import os
import subprocess
import sys

CHECKS: list[list[str]] = [
    [sys.executable, "scripts/preflight_python.py"],
    [sys.executable, "scripts/check_ops_readiness.py"],
    [sys.executable, "scripts/check_env_schema.py"],
    [sys.executable, "scripts/check_secret_patterns.py"],
    [sys.executable, "-m", "ruff", "check", "app", "tests"],
    [sys.executable, "-m", "mypy"],
    [sys.executable, "scripts/check_migration_revisions.py"],
    [sys.executable, "scripts/check_migration_heads.py"],
    [sys.executable, "scripts/check_endpoint_file_sizes.py"],
    [sys.executable, "scripts/check_endpoint_complexity.py"],
    [sys.executable, "scripts/check_critical_indexes.py"],
    [sys.executable, "-m", "pytest", "-q", "-m", "not flaky", "-p", "no:cacheprovider"],
    [sys.executable, "-m", "pip", "check"],
    [sys.executable, "-m", "pip_audit", "-r", "requirements.txt"],
    [sys.executable, "-m", "bandit", "-r", "app", "-ll", "-q"],
    [
        sys.executable,
        "-c",
        (
            "from app.core.config import settings, validate_startup_settings, format_startup_issues; "
            "issues=validate_startup_settings(settings); "
            "print('startup validation passed' if not issues else format_startup_issues(issues)); "
            "raise SystemExit(1 if issues else 0)"
        ),
    ],
]


def _require_module(module_name: str, package_name: str) -> int:
    try:
        importlib.import_module(module_name)
        return 0
    except Exception:
        print(
            f"Missing required tool '{package_name}'. "
            f"Install it first: {sys.executable} -m pip install {package_name}"
        )
        return 1


def _require_python_312() -> int:
    major = sys.version_info.major
    minor = sys.version_info.minor
    if (major, minor) == (3, 12):
        return 0
    print(
        "Python 3.12 is required for release checks. "
        f"Detected {major}.{minor}. "
        "Run with: py -3.12 scripts/check_ready.py (Windows) or python3.12 scripts/check_ready.py (Linux/macOS)."
    )
    return 1


def main() -> int:
    rc = _require_python_312()
    if rc != 0:
        return rc
    for module_name, package_name in (("pip_audit", "pip-audit"), ("bandit", "bandit")):
        rc = _require_module(module_name, package_name)
        if rc != 0:
            return rc
    base_env = os.environ.copy()
    base_env.setdefault("PYTHONUTF8", "1")
    base_env.setdefault("PYTHONIOENCODING", "utf-8")
    for cmd in CHECKS:
        print(f"\n==> {' '.join(cmd)}")
        proc = subprocess.run(cmd, check=False, env=base_env)
        if proc.returncode != 0:
            return proc.returncode
    print("\nAll release checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
