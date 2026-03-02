from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = ROOT / "alembic" / "versions"
_REVISION_RE = re.compile(r'^\s*revision(?:\s*:\s*[^=]+)?\s*=\s*"([^"]+)"\s*$', re.MULTILINE)
_DOWN_REVISION_RE = re.compile(
    r'^\s*down_revision(?:\s*:\s*[^=]+)?\s*=\s*(.+?)\s*$',
    re.MULTILINE,
)
_FILENAME_ID_RE = re.compile(r"^(\d{8})_(\d{4})_")
_FULL_ID_RE = re.compile(r"^\d{8}_\d{4}$")


def _parse_revision(text: str, path: Path) -> str:
    match = _REVISION_RE.search(text)
    if not match:
        raise RuntimeError(f"{path.name}: missing revision declaration")
    return match.group(1).strip()


def _parse_down_revisions(text: str) -> list[str]:
    match = _DOWN_REVISION_RE.search(text)
    if not match:
        return []
    raw = match.group(1).strip()
    if raw in {"None", "null"}:
        return []
    if raw.startswith('"') and raw.endswith('"'):
        return [raw.strip('"')]
    if raw.startswith("'") and raw.endswith("'"):
        return [raw.strip("'")]
    if raw.startswith("(") and raw.endswith(")"):
        body = raw[1:-1].strip()
        if not body:
            return []
        values: list[str] = []
        for token in body.split(","):
            token = token.strip().strip('"').strip("'")
            if token:
                values.append(token)
        return values
    return []


def main() -> int:
    if not VERSIONS_DIR.exists():
        raise RuntimeError(f"Alembic versions directory not found: {VERSIONS_DIR}")

    revisions: dict[str, Path] = {}
    down_refs: list[tuple[Path, str]] = []
    failures: list[str] = []

    for path in sorted(VERSIONS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        revision = _parse_revision(text, path)
        if revision in revisions:
            failures.append(
                f"Duplicate revision id {revision!r} in {path.name} and {revisions[revision].name}"
            )
        revisions[revision] = path

        # Guardrail: for timestamped filenames, enforce full timestamped revision IDs.
        match = _FILENAME_ID_RE.match(path.name)
        if (
            match
            and match.group(1) >= "20260302"
            and not _FULL_ID_RE.fullmatch(revision)
        ):
            failures.append(
                f"{path.name}: revision {revision!r} must use full id format YYYYMMDD_NNNN"
            )

        for down in _parse_down_revisions(text):
            down_refs.append((path, down))
            if (
                match
                and match.group(1) >= "20260302"
                and _FULL_ID_RE.fullmatch(down) is False
                and len(down) <= 4
            ):
                failures.append(
                    f"{path.name}: down_revision {down!r} is ambiguous; use full id format"
                )

    for path, down in down_refs:
        if down not in revisions:
            failures.append(
                f"{path.name}: down_revision {down!r} not found among migration revisions"
            )

    if failures:
        sys.stderr.write("Migration revision integrity check failed:\n")
        for item in failures:
            sys.stderr.write(f"- {item}\n")
        return 1

    sys.stdout.write(f"Migration revision integrity check passed ({len(revisions)} revisions).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
