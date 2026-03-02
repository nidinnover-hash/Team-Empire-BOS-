from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], *, required: bool = True) -> int:
    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    if proc.returncode != 0 and required:
        return proc.returncode
    return 0


def _disk_health() -> int:
    usage = shutil.disk_usage(ROOT)
    free_gb = usage.free / (1024**3)
    sys.stdout.write(f"Disk free: {free_gb:.2f} GiB\n")
    if free_gb < 2.0:
        sys.stdout.write("Low disk space (<2 GiB). npm/pip/test steps may fail with ENOSPC.\n")
        return 1
    return 0


def main() -> int:
    rc = _disk_health()
    if rc != 0:
        return rc

    checks: list[list[str]] = [
        [sys.executable, "--version"],
        [sys.executable, "scripts/preflight_python.py"],
        [sys.executable, "scripts/check_env_schema.py"],
        [sys.executable, "scripts/check_migration_revisions.py"],
        [sys.executable, "scripts/check_migration_heads.py"],
        [sys.executable, "-m", "pip", "check"],
    ]

    for cmd in checks:
        sys.stdout.write(f"\n==> {' '.join(cmd)}\n")
        rc = _run(cmd, required=True)
        if rc != 0:
            return rc

    sys.stdout.write("\nDeveloper environment health check passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
