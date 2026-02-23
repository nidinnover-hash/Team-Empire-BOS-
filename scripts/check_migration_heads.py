from __future__ import annotations

import subprocess
import sys


def _heads() -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    heads: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("Rev:"):
            continue
        rev = line.split(" ", 1)[0]
        if rev and rev != "(head)":
            heads.append(rev)
    return heads


def main() -> int:
    heads = _heads()
    if len(heads) <= 1:
        print(f"Migration heads check passed ({len(heads)} head).")
        return 0
    print("Multiple Alembic heads detected:")
    for head in heads:
        print(f"- {head}")
    print("Resolve with `alembic merge` before merging.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
