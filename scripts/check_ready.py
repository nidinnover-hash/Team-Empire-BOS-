from __future__ import annotations

import importlib
import os
import subprocess
import sys


CHECKS: list[list[str]] = [
    [sys.executable, "scripts/check_ops_readiness.py"],
    [sys.executable, "-m", "ruff", "check", "app", "tests"],
    [sys.executable, "-m", "mypy"],
    [sys.executable, "scripts/check_migration_heads.py"],
    [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
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


def _ensure_tool(module_name: str, package_name: str) -> None:
    try:
        importlib.import_module(module_name)
    except Exception as err:
        print(f"Installing missing tool: {package_name}")
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name],
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to install required tool: {package_name}") from err


def main() -> int:
    _ensure_tool("pip_audit", "pip-audit")
    _ensure_tool("bandit", "bandit")
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
