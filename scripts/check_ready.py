from __future__ import annotations

import subprocess
import sys


CHECKS: list[list[str]] = [
    ["ruff", "check", "app", "tests"],
    [sys.executable, "-m", "mypy", "app", "tests"],
    [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
]


def main() -> int:
    for cmd in CHECKS:
        print(f"\n==> {' '.join(cmd)}")
        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            return proc.returncode
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
