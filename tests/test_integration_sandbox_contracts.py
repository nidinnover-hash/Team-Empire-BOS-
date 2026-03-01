from __future__ import annotations

import os

import httpx
import pytest


def _enabled() -> bool:
    return os.getenv("SANDBOX_CONTRACT_TESTS_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


pytestmark = pytest.mark.skipif(
    not _enabled(),
    reason="Sandbox contract tests disabled (set SANDBOX_CONTRACT_TESTS_ENABLED=true).",
)


@pytest.mark.asyncio
async def test_github_sandbox_contract() -> None:
    token = (os.getenv("SANDBOX_GITHUB_TOKEN") or "").strip()
    if not token:
        pytest.skip("SANDBOX_GITHUB_TOKEN not configured")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("login"), str)


@pytest.mark.asyncio
async def test_slack_sandbox_contract() -> None:
    token = (os.getenv("SANDBOX_SLACK_BOT_TOKEN") or "").strip()
    if not token:
        pytest.skip("SANDBOX_SLACK_BOT_TOKEN not configured")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") is True


@pytest.mark.asyncio
async def test_notion_sandbox_contract() -> None:
    token = (os.getenv("SANDBOX_NOTION_TOKEN") or "").strip()
    if not token:
        pytest.skip("SANDBOX_NOTION_TOKEN not configured")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.notion.com/v1/search",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            json={"page_size": 1},
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert "results" in payload
