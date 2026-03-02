from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "sdk" / "release-notes.md"


def main() -> int:
    if not NOTES.exists():
        raise RuntimeError(f"Release notes file not found: {NOTES}")
    text = NOTES.read_text(encoding="utf-8")
    if "## Highlights" not in text:
        raise RuntimeError("Release notes must include a '## Highlights' section.")
    lines = [line.strip() for line in text.splitlines()]
    try:
        idx = lines.index("## Highlights")
    except ValueError as exc:
        raise RuntimeError("Release notes missing highlights section.") from exc

    highlight_lines = [line for line in lines[idx + 1 :] if line]
    if not highlight_lines:
        raise RuntimeError("Release notes highlights section is empty.")
    if all(line == "- No changelog highlights provided." for line in highlight_lines):
        raise RuntimeError("Release notes must include real highlights, not placeholder text.")
    if not any(line.startswith("- ") for line in highlight_lines):
        raise RuntimeError("Release notes highlights must include bullet items.")

    sys.stdout.write("SDK release notes validation passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
