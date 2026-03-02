from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT_SPEC = ROOT / "sdk" / "openapi" / "openapi.json"
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_base_spec(base_ref: str) -> dict[str, Any] | None:
    candidate_refs = [f"origin/{base_ref}", base_ref]
    for ref in candidate_refs:
        cmd = ["git", "show", f"{ref}:sdk/openapi/openapi.json"]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout)
    return None


def _operation_map(spec: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return out
    for path, raw_item in paths.items():
        if not isinstance(path, str) or not isinstance(raw_item, dict):
            continue
        for method, operation in raw_item.items():
            if method in _HTTP_METHODS and isinstance(operation, dict):
                out[(path, method)] = operation
    return out


def _response_codes(op: dict[str, Any]) -> set[str]:
    responses = op.get("responses", {})
    if not isinstance(responses, dict):
        return set()
    return {str(code) for code in responses if isinstance(code, str)}


def _required_request_fields(op: dict[str, Any], spec: dict[str, Any]) -> set[str]:
    body = op.get("requestBody", {})
    if not isinstance(body, dict):
        return set()
    content = body.get("content", {})
    if not isinstance(content, dict):
        return set()
    app_json = content.get("application/json", {})
    if not isinstance(app_json, dict):
        return set()
    schema = app_json.get("schema", {})
    if not isinstance(schema, dict):
        return set()
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        schema_name = ref.rsplit("/", 1)[-1]
        components = spec.get("components", {}).get("schemas", {})
        if isinstance(components, dict):
            resolved = components.get(schema_name)
            if isinstance(resolved, dict):
                schema = resolved
    required = schema.get("required", [])
    if not isinstance(required, list):
        return set()
    return {str(item) for item in required}


def main() -> int:
    base_ref = os.getenv("GITHUB_BASE_REF", "").strip()
    if not base_ref:
        sys.stdout.write("No GITHUB_BASE_REF set; skipping OpenAPI breaking check.\n")
        return 0

    if not CURRENT_SPEC.exists():
        raise FileNotFoundError(f"Current spec not found: {CURRENT_SPEC}")
    current = _load_json(CURRENT_SPEC)
    previous = _load_base_spec(base_ref)
    if previous is None:
        sys.stdout.write(
            f"Could not load base OpenAPI from {base_ref}; skipping breaking check.\n"
        )
        return 0

    current_ops = _operation_map(current)
    previous_ops = _operation_map(previous)
    failures: list[str] = []

    for op_key, old_op in sorted(previous_ops.items()):
        new_op = current_ops.get(op_key)
        if new_op is None:
            failures.append(f"Removed operation: {op_key[1].upper()} {op_key[0]}")
            continue

        old_codes = _response_codes(old_op)
        new_codes = _response_codes(new_op)
        missing_codes = sorted(old_codes - new_codes)
        if missing_codes:
            failures.append(
                f"Removed response codes in {op_key[1].upper()} {op_key[0]}: {', '.join(missing_codes)}"
            )

        old_required = _required_request_fields(old_op, previous)
        new_required = _required_request_fields(new_op, current)
        added_required = sorted(new_required - old_required)
        if added_required:
            failures.append(
                f"Added required request fields in {op_key[1].upper()} {op_key[0]}: "
                + ", ".join(added_required)
            )

    if failures:
        sys.stderr.write("OpenAPI breaking changes detected:\n")
        for item in failures:
            sys.stderr.write(f"- {item}\n")
        return 1

    sys.stdout.write(f"OpenAPI breaking check passed against base ref {base_ref}.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
