"""Role/page access matrix regression tests for core web surfaces."""

from __future__ import annotations

import pytest

from app.core.security import create_access_token


def _set_web_session(client, *, user_id: int, email: str, role: str, org_id: int = 1) -> None:
    token = create_access_token(
        {
            "id": user_id,
            "email": email,
            "role": role,
            "org_id": org_id,
            "token_version": 1,
        }
    )
    client.cookies.set("pc_session", token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "user_id", "email", "expected"),
    [
        ("CEO", 1, "ceo@org1.com", {"/": 200, "/web/observe": 200, "/web/ops-intel": 200}),
        ("MANAGER", 3, "manager@org1.com", {"/": 200, "/web/observe": 403, "/web/ops-intel": 200}),
        ("STAFF", 4, "staff@org1.com", {"/": 200, "/web/observe": 403, "/web/ops-intel": 403}),
    ],
)
async def test_web_role_access_matrix(client, role: str, user_id: int, email: str, expected: dict[str, int]):
    _set_web_session(client, user_id=user_id, email=email, role=role)

    for route, status_code in expected.items():
        resp = await client.get(route, follow_redirects=False)
        assert resp.status_code == status_code, f"{role} expected {route}={status_code}, got {resp.status_code}"
