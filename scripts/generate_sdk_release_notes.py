from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "sdk" / "CHANGELOG.md"
OPENAPI = ROOT / "sdk" / "openapi" / "openapi.json"
OUT = ROOT / "sdk" / "release-notes.md"
VERSION_RE = re.compile(r"^##\s+([0-9]+\.[0-9]+\.[0-9]+)\s+-\s+([0-9]{4}-[0-9]{2}-[0-9]{2})\s*$")


def _version_from_tag(tag: str) -> str:
    if not tag.startswith("sdk-v"):
        raise RuntimeError(f"Unsupported SDK tag format: {tag!r}")
    return tag[len("sdk-v") :]


def _extract_changelog_section(version: str) -> tuple[str, list[str]]:
    lines = CHANGELOG.read_text(encoding="utf-8").splitlines()
    collecting = False
    date = ""
    body: list[str] = []
    for line in lines:
        m = VERSION_RE.match(line.strip())
        if m:
            current_version, current_date = m.group(1), m.group(2)
            if collecting:
                break
            if current_version == version:
                collecting = True
                date = current_date
                continue
        if collecting:
            body.append(line)
    if not collecting:
        raise RuntimeError(f"Version {version} not found in sdk/CHANGELOG.md")
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return date, body


def _openapi_summary() -> tuple[int, int]:
    raw: dict[str, Any] = json.loads(OPENAPI.read_text(encoding="utf-8"))
    path_count = 0
    operation_count = 0
    for _path, item in raw.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        path_count += 1
        for method, op in item.items():
            if method in {"get", "post", "put", "patch", "delete", "options", "head", "trace"} and isinstance(op, dict):
                operation_count += 1
    return path_count, operation_count


def _git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        return "unknown"
    return proc.stdout.strip() or "unknown"


def main() -> int:
    tag = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not tag:
        raise RuntimeError("Usage: python scripts/generate_sdk_release_notes.py sdk-v<version>")
    version = _version_from_tag(tag)
    date, changelog_lines = _extract_changelog_section(version)
    path_count, operation_count = _openapi_summary()
    sha = _git_sha()

    notes: list[str] = [
        f"# SDK Release {version}",
        "",
        f"- Tag: `{tag}`",
        f"- Date: `{date}`",
        f"- Commit: `{sha}`",
        f"- OpenAPI paths: `{path_count}`",
        f"- OpenAPI operations: `{operation_count}`",
        "",
        "## Highlights",
    ]
    if changelog_lines:
        notes.extend(changelog_lines)
    else:
        notes.append("- No changelog highlights provided.")
    notes.append("")

    OUT.write_text("\n".join(notes) + "\n", encoding="utf-8")
    sys.stdout.write(f"Wrote {OUT}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
