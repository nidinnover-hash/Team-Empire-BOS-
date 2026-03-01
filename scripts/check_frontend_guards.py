"""Fail CI when critical frontend guardrails regress."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Keep this guard focused on the hardened dashboard surface.
CHECKS: dict[str, list[tuple[str, str]]] = {
    "app/static/js/dashboard-page.js": [
        (r"onclick\s*=", "Inline onclick handler found"),
        (r"onchange\s*=", "Inline onchange handler found"),
        (r"insertAdjacentHTML\s*\(", "insertAdjacentHTML usage found"),
        (r"wrap\.innerHTML\s*=", "wrap.innerHTML usage found"),
        (r"events\.map\s*\(", "events.map renderer found; use DOM renderer"),
        (r"entries\.map\s*\(", "entries.map renderer found; use DOM renderer"),
        (r"steps\.map\s*\(", "steps.map renderer found; use DOM renderer"),
    ],
    "app/templates/dashboard.html": [
        (r"onclick\s*=", "Inline onclick handler found in template"),
        (r"onchange\s*=", "Inline onchange handler found in template"),
    ],
}


def main() -> int:
    failures: list[str] = []

    for rel_path, rules in CHECKS.items():
        path = ROOT / rel_path
        if not path.exists():
            failures.append(f"Missing file: {rel_path}")
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for pattern, message in rules:
            if re.search(pattern, content):
                failures.append(f"{rel_path}: {message} ({pattern})")

    if failures:
        print("Frontend guard check failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("Frontend guard check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
