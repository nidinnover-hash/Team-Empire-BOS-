from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "sdk" / "openapi" / "openapi.json"
PY_CLIENT = ROOT / "sdk" / "python" / "nidin_bos_sdk" / "client.py"
TS_CLIENT = ROOT / "sdk" / "typescript" / "src" / "client.ts"

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
_SDK_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/api-keys",
    "/api/v1/webhooks",
    "/api/v1/tasks",
    "/api/v1/approvals",
    "/api/v1/automations",
    "/api/v1/orgs",
)
_PY_SKIP = {
    "auth_me",
    "list_api_keys",
    "create_api_key",
    "revoke_api_key",
    "list_webhooks",
    "create_webhook",
    "list_webhook_deliveries",
    "list_tasks",
    "create_task",
    "update_task",
    "list_approvals",
    "approve_approval",
    "list_organizations",
    "list_automation_triggers",
    "list_automation_workflows",
}
_TS_SKIP = {
    "authMe",
    "listApiKeys",
    "createApiKey",
    "revokeApiKey",
    "listWebhooks",
    "createWebhook",
    "listWebhookDeliveries",
    "listTasks",
    "createTask",
    "updateTask",
    "listApprovals",
    "approveApproval",
    "listOrganizations",
    "listAutomationTriggers",
    "listAutomationWorkflows",
}


def _to_snake(name: str) -> str:
    name = re.sub(r"[^0-9A-Za-z]+", "_", name)
    name = re.sub("([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub("_+", "_", name).strip("_").lower()
    return name or "operation"


def _snake_to_camel(name: str) -> str:
    parts = [part for part in name.split("_") if part]
    if not parts:
        return "operation"
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _path_params(path: str) -> list[str]:
    return re.findall(r"{([^}]+)}", path)


def _query_params(op: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for param in op.get("parameters", []):
        if not isinstance(param, dict):
            continue
        if param.get("in") != "query":
            continue
        name = param.get("name")
        if isinstance(name, str):
            out.append(_to_snake(name))
    return list(dict.fromkeys(out))


def _has_json_body(op: dict[str, Any]) -> bool:
    content = op.get("requestBody", {}).get("content", {})
    return isinstance(content, dict) and "application/json" in content


def _expected_statuses(op: dict[str, Any]) -> list[int]:
    responses = op.get("responses", {})
    if not isinstance(responses, dict):
        return [200]
    out: list[int] = []
    for code in responses:
        if not isinstance(code, str) or not code.isdigit():
            continue
        numeric = int(code)
        if 200 <= numeric < 300:
            out.append(numeric)
    return sorted(set(out)) or [200]


def _iter_operations(spec: dict[str, Any]) -> list[tuple[str, str, str, dict[str, Any]]]:
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return []
    operations: list[tuple[str, str, str, dict[str, Any]]] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        if not any(path.startswith(prefix) for prefix in _SDK_PREFIXES):
            continue
        for method, op in path_item.items():
            if method not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            operation_id = op.get("operationId")
            if not isinstance(operation_id, str) or not operation_id.strip():
                continue
            operations.append((operation_id.strip(), path, method.upper(), op))
    operations.sort(key=lambda item: item[0])
    return operations


def _render_py_methods(ops: list[tuple[str, str, str, dict[str, Any]]]) -> str:
    lines: list[str] = []
    for op_id, path, method, op in ops:
        name = _to_snake(op_id)
        if name in _PY_SKIP:
            continue
        path_params = _path_params(path)
        query_params = _query_params(op)
        has_body = _has_json_body(op)
        status_codes = _expected_statuses(op)

        signature_parts = ["self"]
        signature_parts.extend(f"{param}: Any" for param in path_params)
        if has_body:
            signature_parts.append("payload: dict[str, Any] | None = None")
        signature_parts.extend(f"{q}: Any | None = None" for q in query_params)
        lines.append(f"    def {name}({', '.join(signature_parts)}) -> Any:")
        if path_params:
            f_path = path
            for param in path_params:
                f_path = f_path.replace(f"{{{param}}}", "{" + param + "}")
            lines.append(f'        path = f"{f_path}"')
        else:
            lines.append(f'        path = "{path}"')

        if query_params:
            lines.append("        params = {")
            for q in query_params:
                lines.append(f'            "{q}": {q},')
            lines.append("        }")
            lines.append("        params = {k: v for k, v in params.items() if v is not None}")
            lines.append("        if not params:")
            lines.append("            params = None")
        else:
            lines.append("        params = None")

        if len(status_codes) == 1:
            expected = str(status_codes[0])
        else:
            expected = "(" + ", ".join(str(code) for code in status_codes) + ")"
        json_body = "payload" if has_body else "None"
        lines.extend(
            [
                "        return self._request_json(",
                f'            method="{method}",',
                "            path=path,",
                f"            json_body={json_body},",
                "            params=params,",
                f"            expected_status={expected},",
                "        )",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_ts_methods(ops: list[tuple[str, str, str, dict[str, Any]]]) -> str:
    lines: list[str] = []
    for op_id, path, method, op in ops:
        snake_name = _to_snake(op_id)
        name = _snake_to_camel(snake_name)
        if name in _TS_SKIP:
            continue
        path_params = _path_params(path)
        query_params = _query_params(op)
        has_body = _has_json_body(op)
        status_codes = _expected_statuses(op)

        signature: list[str] = [f"{param}: string | number" for param in path_params]
        if has_body:
            signature.append("payload?: Record<string, unknown>")
        signature.extend(f"{q}?: string | number | boolean" for q in query_params)
        lines.append(f"  {name}({', '.join(signature)}): Promise<unknown> {{")
        path_expr = path
        for param in path_params:
            path_expr = path_expr.replace("{" + param + "}", "${String(" + param + ")}")
        lines.append(f"    let path = `{path_expr}`;")

        if query_params:
            lines.append("    const query = new URLSearchParams();")
            for q in query_params:
                lines.append(f"    if ({q} !== undefined) query.set(\"{q}\", String({q}));")
            lines.append("    const qs = query.toString();")
            lines.append("    if (qs) path = `${path}?${qs}`;")

        expected = ", ".join(str(code) for code in status_codes)
        if has_body:
            lines.extend(
                [
                    "    return this.request<unknown>("
                    f'"{method}", path, {{',
                    "      body: payload,",
                    f"      expectedStatus: [{expected}],",
                    "    });",
                    "  }",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "    return this.request<unknown>("
                    f'"{method}", path, {{',
                    f"      expectedStatus: [{expected}],",
                    "    });",
                    "  }",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _replace_between_markers(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError(f"Missing markers: {start_marker} / {end_marker}")
    prefix = text[: start + len(start_marker)]
    suffix = text[end:]
    return prefix + "\n" + replacement + suffix


def main() -> int:
    if not OPENAPI_PATH.exists():
        raise FileNotFoundError(
            f"OpenAPI schema not found at {OPENAPI_PATH}. Run scripts/export_openapi_schema.py first."
        )
    spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    ops = _iter_operations(spec)

    py_text = PY_CLIENT.read_text(encoding="utf-8")
    ts_text = TS_CLIENT.read_text(encoding="utf-8")

    py_generated = _render_py_methods(ops)
    ts_generated = _render_ts_methods(ops)

    py_updated = _replace_between_markers(
        py_text,
        "    # BEGIN GENERATED OPERATIONS",
        "    # END GENERATED OPERATIONS",
        py_generated,
    )
    ts_updated = _replace_between_markers(
        ts_text,
        "  // BEGIN GENERATED OPERATIONS",
        "  // END GENERATED OPERATIONS",
        ts_generated,
    )

    PY_CLIENT.write_text(py_updated, encoding="utf-8")
    TS_CLIENT.write_text(ts_updated, encoding="utf-8")
    sys.stdout.write(f"Updated generated Python SDK methods in {PY_CLIENT}\n")
    sys.stdout.write(f"Updated generated TypeScript SDK methods in {TS_CLIENT}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
