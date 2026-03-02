from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = "sdk/python/pyproject.toml"
TS_PACKAGE = "sdk/typescript/package.json"
CHANGELOG = "sdk/CHANGELOG.md"

_VERSION_RE = re.compile(r'^\s*version\s*=\s*"([^"]+)"\s*$', re.MULTILINE)
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_TIER_RANK = {"patch": 0, "minor": 1, "major": 2}


def _run_git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def _changed_files(base_ref: str) -> list[str]:
    subprocess.run(
        ["git", "fetch", "--no-tags", "--depth=1", "origin", base_ref],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    out = _run_git(["diff", "--name-only", f"origin/{base_ref}...HEAD"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def _read_version_from_text(path: str, text: str) -> str:
    if path.endswith(".toml"):
        match = _VERSION_RE.search(text)
        if not match:
            raise RuntimeError(f"Unable to parse version from {path}")
        return match.group(1).strip()
    if path.endswith(".json"):
        obj = json.loads(text)
        version = str(obj.get("version", "")).strip()
        if not version:
            raise RuntimeError(f"Unable to parse version from {path}")
        return version
    raise RuntimeError(f"Unsupported version file: {path}")


def _version_at_ref(path: str, git_ref: str) -> str:
    text = _run_git(["show", f"{git_ref}:{path}"])
    return _read_version_from_text(path, text)


def _version_worktree(path: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    return _read_version_from_text(path, text)


def _parse_semver(version: str) -> tuple[int, int, int]:
    match = _SEMVER_RE.fullmatch(version.strip())
    if not match:
        raise RuntimeError(f"Invalid semver version: {version!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _bump_tier(before: str, after: str) -> Literal["none", "patch", "minor", "major"]:
    b = _parse_semver(before)
    a = _parse_semver(after)
    if a == b:
        return "none"
    if a[0] > b[0]:
        return "major"
    if a[1] > b[1]:
        return "minor"
    if a[2] > b[2]:
        return "patch"
    raise RuntimeError(f"Version decreased or invalid bump: {before!r} -> {after!r}")


def _required_tier(base_ref: str) -> Literal["patch", "minor", "major"]:
    env = os.environ.copy()
    env["GITHUB_BASE_REF"] = base_ref
    proc = subprocess.run(
        [sys.executable, "scripts/check_openapi_change_tier.py"],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "OpenAPI tier check failed")
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("OPENAPI_CHANGE_TIER="):
            value = line.split("=", 1)[1].strip()
            if value in _TIER_RANK:
                return value  # type: ignore[return-value]
    return "patch"


def main() -> int:
    gh_base_ref = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not gh_base_ref:
        gh_base_ref = str(os.environ.get("GITHUB_BASE_REF", "")).strip()
    if not gh_base_ref:
        sys.stdout.write("SDK version bump check skipped: GITHUB_BASE_REF is not set.\n")
        return 0

    changed = _changed_files(gh_base_ref)
    sdk_changed = any(
        path.startswith("sdk/python/nidin_bos_sdk/")
        or path.startswith("sdk/typescript/src/")
        or path == "sdk/openapi/openapi.json"
        for path in changed
    )
    if not sdk_changed:
        sys.stdout.write("SDK version bump check passed: no SDK surface changes detected.\n")
        return 0

    py_base = _version_at_ref(PYPROJECT, f"origin/{gh_base_ref}")
    py_head = _version_worktree(PYPROJECT)
    ts_base = _version_at_ref(TS_PACKAGE, f"origin/{gh_base_ref}")
    ts_head = _version_worktree(TS_PACKAGE)
    changelog_changed = CHANGELOG in changed
    required_tier = _required_tier(gh_base_ref)
    py_bump = _bump_tier(py_base, py_head)
    ts_bump = _bump_tier(ts_base, ts_head)

    failures: list[str] = []
    if py_base == py_head:
        failures.append(f"Python SDK version was not bumped ({py_head}).")
    if ts_base == ts_head:
        failures.append(f"TypeScript SDK version was not bumped ({ts_head}).")
    if _TIER_RANK.get(py_bump, -1) < _TIER_RANK[required_tier]:
        failures.append(
            f"Python SDK version bump {py_base} -> {py_head} is '{py_bump}', "
            f"but OpenAPI change tier requires at least '{required_tier}'."
        )
    if _TIER_RANK.get(ts_bump, -1) < _TIER_RANK[required_tier]:
        failures.append(
            f"TypeScript SDK version bump {ts_base} -> {ts_head} is '{ts_bump}', "
            f"but OpenAPI change tier requires at least '{required_tier}'."
        )
    if not changelog_changed:
        failures.append("sdk/CHANGELOG.md must be updated for SDK-facing changes.")

    if failures:
        sys.stdout.write("SDK version bump check failed:\n")
        for item in failures:
            sys.stdout.write(f"- {item}\n")
        return 1

    sys.stdout.write(f"SDK version bump check passed (required tier: {required_tier}).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
