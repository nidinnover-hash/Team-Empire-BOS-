from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "sdk" / "openapi" / "openapi.json"
PY_OUT = ROOT / "sdk" / "python" / "nidin_bos_sdk" / "models.py"
TS_OUT = ROOT / "sdk" / "typescript" / "src" / "types.ts"

_ROOT_COMPONENTS = [
    "ApiKeyCreate",
    "ApiKeyCreateResponse",
    "ApiKeyListResponse",
]

_ROOT_OPERATION_PATH_PREFIXES = [
    "/api/v1/auth/me",
    "/api/v1/api-keys",
    "/api/v1/contacts",
    "/api/v1/webhooks",
    "/api/v1/tasks",
    "/api/v1/approvals",
    "/api/v1/automations",
    "/api/v1/orgs",
]
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def _iter_refs(node: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            refs.append(ref.rsplit("/", 1)[-1])
        for value in node.values():
            refs.extend(_iter_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.extend(_iter_refs(item))
    return refs


def _collect_operation_refs(paths: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        if not any(path.startswith(prefix) for prefix in _ROOT_OPERATION_PATH_PREFIXES):
            continue
        for method, op in path_item.items():
            if method not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            request_schema = (
                op.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            if isinstance(request_schema, dict):
                refs.update(_iter_refs(request_schema))
            for resp in (op.get("responses") or {}).values():
                if not isinstance(resp, dict):
                    continue
                resp_schema = (
                    resp.get("content", {})
                    .get("application/json", {})
                    .get("schema")
                )
                if isinstance(resp_schema, dict):
                    refs.update(_iter_refs(resp_schema))
    return refs


def _collect_schemas(components: dict[str, Any], paths: dict[str, Any]) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    stack = list(dict.fromkeys(_ROOT_COMPONENTS + list(_collect_operation_refs(paths))))
    while stack:
        name = stack.pop()
        if name in selected:
            continue
        schema = components.get(name)
        if not isinstance(schema, dict):
            continue
        selected[name] = schema
        for ref_name in _iter_refs(schema):
            if ref_name not in selected:
                stack.append(ref_name)
    return selected


def _py_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return str(schema["$ref"]).rsplit("/", 1)[-1]
    if "enum" in schema and isinstance(schema["enum"], list):
        literals = [repr(item) for item in schema["enum"]]
        if literals:
            return "Literal[" + ", ".join(literals) + "]"
    schema_type = schema.get("type")
    if schema_type == "string":
        return "str"
    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "float"
    if schema_type == "boolean":
        return "bool"
    if schema_type == "null":
        return "None"
    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            return f"list[{_py_type(items)}]"
        return "list[Any]"
    if schema_type == "object":
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return f"dict[str, {_py_type(additional)}]"
        return "dict[str, Any]"
    if "anyOf" in schema and isinstance(schema["anyOf"], list):
        members = [_py_type(item) for item in schema["anyOf"] if isinstance(item, dict)]
        members = list(dict.fromkeys(members))
        if "Any" in members and len(members) > 1:
            members = [m for m in members if m != "Any"]
        return " | ".join(members) if members else "Any"
    if "oneOf" in schema and isinstance(schema["oneOf"], list):
        members = [_py_type(item) for item in schema["oneOf"] if isinstance(item, dict)]
        members = list(dict.fromkeys(members))
        if "Any" in members and len(members) > 1:
            members = [m for m in members if m != "Any"]
        return " | ".join(members) if members else "Any"
    return "Any"


def _ts_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return str(schema["$ref"]).rsplit("/", 1)[-1]
    if "enum" in schema and isinstance(schema["enum"], list):
        literals = [json.dumps(item) for item in schema["enum"]]
        if literals:
            return " | ".join(literals)
    schema_type = schema.get("type")
    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            return f"{_ts_type(items)}[]"
        return "unknown[]"
    if schema_type == "object":
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return f"Record<string, {_ts_type(additional)}>"
        return "Record<string, unknown>"
    if "anyOf" in schema and isinstance(schema["anyOf"], list):
        members = [_ts_type(item) for item in schema["anyOf"] if isinstance(item, dict)]
        members = list(dict.fromkeys(members))
        if "unknown" in members and len(members) > 1:
            members = [m for m in members if m != "unknown"]
        return " | ".join(members) if members else "unknown"
    if "oneOf" in schema and isinstance(schema["oneOf"], list):
        members = [_ts_type(item) for item in schema["oneOf"] if isinstance(item, dict)]
        members = list(dict.fromkeys(members))
        if "unknown" in members and len(members) > 1:
            members = [m for m in members if m != "unknown"]
        return " | ".join(members) if members else "unknown"
    return "unknown"


def _render_python_models(schemas: dict[str, dict[str, Any]]) -> str:
    body_lines: list[str] = [
        "from __future__ import annotations",
    ]
    for name in sorted(schemas):
        schema = schemas[name]
        schema_type = schema.get("type")
        props = schema.get("properties")
        required = set(schema.get("required", [])) if isinstance(schema.get("required"), list) else set()
        if schema_type == "object" and isinstance(props, dict):
            body_lines.append(f"class {name}(TypedDict):")
            if not props:
                body_lines.append("    pass")
            else:
                for prop_name, prop_schema in props.items():
                    if not isinstance(prop_schema, dict):
                        prop_type = "Any"
                    else:
                        prop_type = _py_type(prop_schema)
                    if prop_name not in required:
                        prop_type = f"NotRequired[{prop_type}]"
                    body_lines.append(f"    {prop_name}: {prop_type}")
            body_lines.append("")
            continue
        body_lines.append(f"{name} = {_py_type(schema)}")
        body_lines.append("")

    body_lines.append("WebhookEndpointListResponse = list[WebhookEndpointRead]")
    body_lines.append("")

    imports = {"NotRequired", "TypedDict"}
    body = "\n".join(body_lines)
    if "Any" in body:
        imports.add("Any")
    if "Literal" in body:
        imports.add("Literal")
    header = f"from typing import {', '.join(sorted(imports))}\n\n"
    generated_comment = "# Generated from sdk/openapi/openapi.json by scripts/generate_sdk_models.py\n\n"
    return "\n".join(body_lines[:1]) + "\n\n" + header + generated_comment + "\n".join(body_lines[1:])


def _render_ts_models(schemas: dict[str, dict[str, Any]]) -> str:
    lines = [
        "// Generated from sdk/openapi/openapi.json by scripts/generate_sdk_models.py",
        "",
    ]
    for name in sorted(schemas):
        schema = schemas[name]
        schema_type = schema.get("type")
        props = schema.get("properties")
        required = set(schema.get("required", [])) if isinstance(schema.get("required"), list) else set()
        if schema_type == "object" and isinstance(props, dict):
            lines.append(f"export interface {name} {{")
            for prop_name, prop_schema in props.items():
                ts_type = _ts_type(prop_schema) if isinstance(prop_schema, dict) else "unknown"
                optional = "" if prop_name in required else "?"
                lines.append(f"  {prop_name}{optional}: {ts_type};")
            lines.append("}")
            lines.append("")
            continue
        lines.append(f"export type {name} = {_ts_type(schema)};")
        lines.append("")

    lines.append("export type WebhookEndpointListResponse = WebhookEndpointRead[];")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not OPENAPI_PATH.exists():
        raise FileNotFoundError(
            f"OpenAPI schema not found at {OPENAPI_PATH}. Run scripts/export_openapi_schema.py first."
        )
    raw = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    components = raw.get("components", {}).get("schemas", {})
    paths = raw.get("paths", {})
    if not isinstance(components, dict):
        raise RuntimeError("OpenAPI components.schemas missing or invalid")
    if not isinstance(paths, dict):
        raise RuntimeError("OpenAPI paths missing or invalid")
    selected = _collect_schemas(components, paths)

    PY_OUT.parent.mkdir(parents=True, exist_ok=True)
    TS_OUT.parent.mkdir(parents=True, exist_ok=True)
    PY_OUT.write_text(_render_python_models(selected), encoding="utf-8")
    TS_OUT.write_text(_render_ts_models(selected), encoding="utf-8")
    sys.stdout.write(f"Wrote Python models to {PY_OUT}\n")
    sys.stdout.write(f"Wrote TypeScript types to {TS_OUT}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
