from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts"
OUT_MD = OUT_DIR / "ci-risk-report.md"
OUT_JSON = OUT_DIR / "ci-risk-report.json"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _changed_files(base_ref: str) -> list[str]:
    _run(["git", "fetch", "--no-tags", "--depth=1", "origin", base_ref])
    proc = _run(["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"])
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _level(score: int) -> str:
    if score >= 7:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def _summary(base_ref: str) -> dict[str, object]:
    changed = _changed_files(base_ref)
    changed_set = set(changed)

    migration_score = 2
    if any(path.startswith("alembic/versions/") for path in changed_set):
        migration_score = 8
    elif any(path.startswith("app/models/") for path in changed_set):
        migration_score = 5

    api_score = 2
    if any(path.startswith("app/api/") for path in changed_set):
        api_score = 7
    if "sdk/openapi/openapi.json" in changed_set:
        api_score = max(api_score, 5)

    sdk_score = 2
    if any(path.startswith("sdk/python/nidin_bos_sdk/") for path in changed_set):
        sdk_score = 6
    if any(path.startswith("sdk/typescript/src/") for path in changed_set):
        sdk_score = max(sdk_score, 6)
    if "scripts/generate_sdk_models.py" in changed_set:
        sdk_score = max(sdk_score, 7)

    dep_score = 2
    if any(path.startswith("requirements") for path in changed_set):
        dep_score = 7
    if "package.json" in changed_set:
        dep_score = max(dep_score, 6)

    flaky_count = 0
    for test_path in ROOT.glob("tests/test_*.py"):
        text = test_path.read_text(encoding="utf-8")
        flaky_count += len(re.findall(r"@pytest\.mark\.flaky", text))
    flaky_score = 2 if flaky_count == 0 else (5 if flaky_count < 20 else 8)

    return {
        "base_ref": base_ref,
        "changed_files": len(changed),
        "risks": [
            {"area": "migration", "score": migration_score, "level": _level(migration_score)},
            {"area": "api_contract", "score": api_score, "level": _level(api_score)},
            {"area": "sdk_drift", "score": sdk_score, "level": _level(sdk_score)},
            {"area": "flaky_tests", "score": flaky_score, "level": _level(flaky_score), "count": flaky_count},
            {"area": "dependencies", "score": dep_score, "level": _level(dep_score)},
        ],
    }


def _write_outputs(payload: dict[str, object]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# CI Risk Report",
        "",
        f"- Base ref: `{payload['base_ref']}`",
        f"- Changed files: `{payload['changed_files']}`",
        "",
        "| Area | Score | Level |",
        "|---|---:|---|",
    ]
    for item in payload["risks"]:  # type: ignore[index]
        lines.append(f"| {item['area']} | {item['score']} | {item['level']} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    base_ref = str(os.getenv("GITHUB_BASE_REF", "main")).strip() or "main"
    payload = _summary(base_ref)
    _write_outputs(payload)
    sys.stdout.write(f"Wrote {OUT_MD}\n")
    sys.stdout.write(f"Wrote {OUT_JSON}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
