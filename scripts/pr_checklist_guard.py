from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_DEV_GATE_RE = re.compile(r"-\s*\[[xX]\]\s*`?py\s*-?3\.12\s+scripts/dev_gate\.py`?")
_CHECK_READY_RE = re.compile(r"-\s*\[[xX]\]\s*`?py\s*-?3\.12\s+scripts/check_ready\.py`?")
_MIGRATION_REVIEWED_RE = re.compile(r"-\s*\[[xX]\]\s*migration impact reviewed")
_SDK_UPDATED_RE = re.compile(
    r"-\s*\[[xX]\]\s*sdk version \+\s*`?sdk/changelog\.md`?\s*updated",
)


def evaluate_pr_checklist(body: str, paths: list[str]) -> list[str]:
    lowered = body.lower()
    errors: list[str] = []

    dev_gate_checked = _DEV_GATE_RE.search(lowered) is not None
    check_ready_checked = _CHECK_READY_RE.search(lowered) is not None
    if not dev_gate_checked and not check_ready_checked:
        errors.append(
            "Checklist requires at least one of `scripts/dev_gate.py` or "
            "`scripts/check_ready.py` to be checked."
        )

    migration_touched = any(
        path.startswith("alembic/versions/") or path.startswith("app/models/")
        for path in paths
    )
    migration_reviewed = _MIGRATION_REVIEWED_RE.search(lowered) is not None
    if migration_touched and not migration_reviewed:
        errors.append(
            "Migration/model changes detected; check `Migration impact reviewed` in PR checklist."
        )

    contract_touched = any(
        path == "sdk/openapi/openapi.json"
        or path.startswith("app/api/")
        or path.startswith("app/schemas/")
        for path in paths
    )
    sdk_updated = _SDK_UPDATED_RE.search(lowered) is not None
    if contract_touched and not sdk_updated:
        errors.append(
            "API/OpenAPI contract changes detected; check `SDK version + sdk/CHANGELOG.md "
            "updated...` in PR checklist."
        )
    return errors


def _load_paths(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise RuntimeError("Paths input must be a JSON list.")
    out = [str(item).strip() for item in raw if str(item).strip()]
    return out


def main() -> int:
    if len(sys.argv) != 3:
        raise RuntimeError(
            "Usage: python scripts/pr_checklist_guard.py <pr_body_file> <pr_paths_json_file>"
        )
    body_file = Path(sys.argv[1])
    paths_file = Path(sys.argv[2])
    body = body_file.read_text(encoding="utf-8")
    paths = _load_paths(paths_file)
    failures = evaluate_pr_checklist(body=body, paths=paths)
    if failures:
        sys.stderr.write("PR checklist guard failed:\n")
        for failure in failures:
            sys.stderr.write(f"- {failure}\n")
        return 1
    sys.stdout.write("PR checklist guard passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
