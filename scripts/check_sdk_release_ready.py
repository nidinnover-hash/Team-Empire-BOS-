from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "sdk" / "python" / "pyproject.toml"
TS_PACKAGE = ROOT / "sdk" / "typescript" / "package.json"
CHANGELOG = ROOT / "sdk" / "CHANGELOG.md"
VERSION_RE = re.compile(r'^\s*version\s*=\s*"([^"]+)"\s*$', re.MULTILINE)


def _py_version() -> str:
    match = VERSION_RE.search(PYPROJECT.read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError("Unable to parse Python SDK version")
    return match.group(1).strip()


def _ts_version() -> str:
    pkg = json.loads(TS_PACKAGE.read_text(encoding="utf-8"))
    version = str(pkg.get("version", "")).strip()
    if not version:
        raise RuntimeError("Unable to parse TypeScript SDK version")
    return version


def _tag_version() -> str:
    tag = str(os.environ.get("GITHUB_REF_NAME", "")).strip()
    if not tag and len(sys.argv) > 1:
        tag = sys.argv[1].strip()
    if not tag:
        raise RuntimeError("Tag name not provided (GITHUB_REF_NAME)")
    if not tag.startswith("sdk-v"):
        raise RuntimeError(f"Invalid SDK tag format: {tag!r}. Expected sdk-v<version>.")
    return tag[len("sdk-v"):]


def main() -> int:
    tag_version = _tag_version()
    py_version = _py_version()
    ts_version = _ts_version()
    changelog = CHANGELOG.read_text(encoding="utf-8")
    failures: list[str] = []
    if py_version != tag_version:
        failures.append(f"Python SDK version {py_version} does not match tag {tag_version}")
    if ts_version != tag_version:
        failures.append(f"TypeScript SDK version {ts_version} does not match tag {tag_version}")
    if f"## {tag_version}" not in changelog:
        failures.append(f"CHANGELOG missing section for version {tag_version}")

    if failures:
        sys.stdout.write("SDK release readiness failed:\n")
        for item in failures:
            sys.stdout.write(f"- {item}\n")
        return 1

    sys.stdout.write("SDK release readiness passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
