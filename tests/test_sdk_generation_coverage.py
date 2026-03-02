from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.generate_sdk_clients import (
    _SDK_PREFIXES,
    _PY_SKIP,
    _TS_SKIP,
    _snake_to_camel,
    _to_snake,
)

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "sdk" / "openapi" / "openapi.json"
PY_CLIENT = ROOT / "sdk" / "python" / "nidin_bos_sdk" / "client.py"
TS_CLIENT = ROOT / "sdk" / "typescript" / "src" / "client.ts"


def _extract_block(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    end = text.find(end_marker)
    assert start >= 0 and end > start
    return text[start:end]


def _eligible_get_operation_ids() -> list[str]:
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    op_ids: list[str] = []
    for path, item in spec.get("paths", {}).items():
        if not isinstance(path, str) or not isinstance(item, dict):
            continue
        if not any(path.startswith(prefix) for prefix in _SDK_PREFIXES):
            continue
        op = item.get("get")
        if not isinstance(op, dict):
            continue
        op_id = op.get("operationId")
        if isinstance(op_id, str) and op_id.strip():
            op_ids.append(op_id.strip())
    return sorted(set(op_ids))


def test_python_generated_client_covers_eligible_get_operations() -> None:
    text = PY_CLIENT.read_text(encoding="utf-8")
    block = _extract_block(text, "    # BEGIN GENERATED OPERATIONS", "    # END GENERATED OPERATIONS")
    generated = set(re.findall(r"^\s+def\s+([a-zA-Z_][a-zA-Z0-9_]*)\(", block, flags=re.MULTILINE))

    missing: list[str] = []
    for op_id in _eligible_get_operation_ids():
        method = _to_snake(op_id)
        if method in _PY_SKIP:
            continue
        if method not in generated:
            missing.append(method)
    assert not missing, f"Missing generated Python GET methods: {missing}"


def test_typescript_generated_client_covers_eligible_get_operations() -> None:
    text = TS_CLIENT.read_text(encoding="utf-8")
    block = _extract_block(text, "  // BEGIN GENERATED OPERATIONS", "  // END GENERATED OPERATIONS")
    generated = set(re.findall(r"^\s+([a-zA-Z_][a-zA-Z0-9_]*)\(", block, flags=re.MULTILINE))

    missing: list[str] = []
    for op_id in _eligible_get_operation_ids():
        method = _snake_to_camel(_to_snake(op_id))
        if method in _TS_SKIP:
            continue
        if method not in generated:
            missing.append(method)
    assert not missing, f"Missing generated TypeScript GET methods: {missing}"
