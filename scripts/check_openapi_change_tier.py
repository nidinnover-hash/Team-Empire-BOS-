from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT_SPEC = ROOT / "sdk" / "openapi" / "openapi.json"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
RANK = {"patch": 0, "minor": 1, "major": 2}


def _max_tier(a: str, b: str) -> str:
    return a if RANK[a] >= RANK[b] else b


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_base_spec(base_ref: str) -> dict[str, Any] | None:
    for ref in (f"origin/{base_ref}", base_ref):
        proc = subprocess.run(
            ["git", "show", f"{ref}:sdk/openapi/openapi.json"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout)
    return None


def _ops(spec: dict[str, Any]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return out
    for path, item in paths.items():
        if not isinstance(path, str) or not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method in HTTP_METHODS and isinstance(op, dict):
                out.add((path, method))
    return out


def _required_fields(op: dict[str, Any], spec: dict[str, Any]) -> set[str]:
    req = (
        op.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    if not isinstance(req, dict):
        return set()
    ref = req.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        name = ref.rsplit("/", 1)[-1]
        req = spec.get("components", {}).get("schemas", {}).get(name, {})
    if not isinstance(req, dict):
        return set()
    required = req.get("required", [])
    if not isinstance(required, list):
        return set()
    return {str(x) for x in required}


def _op_map(spec: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    m: dict[tuple[str, str], dict[str, Any]] = {}
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return m
    for path, item in paths.items():
        if not isinstance(path, str) or not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method in HTTP_METHODS and isinstance(op, dict):
                m[(path, method)] = op
    return m


def main() -> int:
    base_ref = os.getenv("GITHUB_BASE_REF", "").strip()
    if not base_ref:
        sys.stdout.write("No GITHUB_BASE_REF set; skipping OpenAPI tier check.\n")
        return 0
    if not CURRENT_SPEC.exists():
        raise FileNotFoundError(f"Missing current OpenAPI: {CURRENT_SPEC}")

    current = _load_json(CURRENT_SPEC)
    base = _load_base_spec(base_ref)
    if base is None:
        sys.stdout.write(f"Could not load base OpenAPI from {base_ref}; skipping tier check.\n")
        return 0

    tier = "patch"
    details: list[str] = []
    base_ops = _ops(base)
    current_ops = _ops(current)

    removed_ops = sorted(base_ops - current_ops)
    added_ops = sorted(current_ops - base_ops)
    if removed_ops:
        tier = _max_tier(tier, "major")
        details.append(f"removed_ops={len(removed_ops)}")
    if added_ops:
        tier = _max_tier(tier, "minor")
        details.append(f"added_ops={len(added_ops)}")

    base_map = _op_map(base)
    current_map = _op_map(current)
    for key in sorted(base_ops & current_ops):
        old_required = _required_fields(base_map[key], base)
        new_required = _required_fields(current_map[key], current)
        if new_required - old_required:
            tier = _max_tier(tier, "major")
            details.append(f"added_required={key[1].upper()} {key[0]}")

    sys.stdout.write(f"OPENAPI_CHANGE_TIER={tier}\n")
    if details:
        sys.stdout.write("OPENAPI_CHANGE_DETAILS=" + "; ".join(details) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
