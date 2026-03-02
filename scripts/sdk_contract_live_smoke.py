from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SDK_PYTHON = ROOT / "sdk" / "python"
if str(SDK_PYTHON) not in sys.path:
    sys.path.insert(0, str(SDK_PYTHON))


def _env(name: str, default: str) -> str:
    value = str(os.environ.get(name, default)).strip()
    if not value:
        raise RuntimeError(f"Required env var {name} is empty")
    return value


def _login(base_url: str, email: str, password: str) -> str:
    with httpx.Client(base_url=base_url, timeout=20.0) as client:
        response = client.post(
            "/token",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("access_token", "")).strip()
        if not token:
            raise RuntimeError("Login response missing access_token")
        return token


def _create_api_key(base_url: str, bearer_token: str) -> str:
    with httpx.Client(base_url=base_url, timeout=20.0) as client:
        response = client.post(
            "/api/v1/api-keys",
            json={"name": "SDK Contract Key", "scopes": "*"},
            headers={"Authorization": f"Bearer {bearer_token}"},
        )
        response.raise_for_status()
        payload = response.json()
        key = str(payload.get("key", "")).strip()
        if not key:
            raise RuntimeError("API key create response missing key")
        return key


def main() -> int:
    from nidin_bos_sdk import NidinBOSClient

    base_url = _env("SDK_BASE_URL", "http://127.0.0.1:8000")
    admin_email = _env("ADMIN_EMAIL", "demo@ai.com")
    admin_password = _env("ADMIN_PASSWORD", "DemoPass123!")

    jwt = _login(base_url, admin_email, admin_password)
    sdk_key = _create_api_key(base_url, jwt)

    with NidinBOSClient(base_url=base_url, api_key=sdk_key) as client:
        me = client.auth_me()
        if str(me.get("email", "")).lower() != admin_email.lower():
            raise RuntimeError("SDK auth_me returned unexpected user email")

        _ = client.list_api_keys()
        _ = client.list_webhooks()

        created = client.create_task(
            {
                "title": "sdk-contract-task",
                "description": "created from python SDK contract smoke",
            }
        )
        task_id = int(created["id"])
        updated = client.update_task(task_id, {"description": "updated by python sdk"})
        if int(updated["id"]) != task_id:
            raise RuntimeError("SDK update_task returned mismatched task id")

        _ = client.list_tasks()
        _ = client.list_approvals()
        _ = client.list_organizations()
        _ = client.list_automation_triggers()
        _ = client.list_automation_workflows()

    sys.stdout.write("Python SDK live contract smoke passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
