from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Guardrails to prevent endpoint modules from becoming unreviewable blobs.
MAX_LINES_BY_FILE: dict[str, int] = {
    "app/api/v1/endpoints/integrations.py": 700,
    "app/api/v1/endpoints/ops.py": 950,
    "app/api/v1/endpoints/admin.py": 700,
}


def _line_count(path: Path) -> int:
    return sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore"))


def main() -> int:
    failures: list[str] = []
    for rel, max_lines in MAX_LINES_BY_FILE.items():
        full = ROOT / rel
        if not full.exists():
            failures.append(f"Missing guarded endpoint file: {rel}")
            continue
        lines = _line_count(full)
        if lines > max_lines:
            failures.append(f"{rel} has {lines} lines (max {max_lines})")

    if failures:
        print("Endpoint size guard failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Endpoint size guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
