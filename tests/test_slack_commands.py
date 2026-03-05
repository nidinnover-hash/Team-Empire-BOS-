"""Tests for the Slack command interface."""

import hashlib
import hmac
import time
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import pytest

from app.api.v1.endpoints import slack_commands
from app.core.config import settings


def _slack_signature(secret: str, timestamp: str, body: bytes) -> str:
    base = f"v0:{timestamp}:{body.decode()}"
    return "v0=" + hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()


async def _post_slack_command(client, *, text: str, user_name: str = "nidin", team_id: str = "T_TEST") -> object:
    body = urlencode({"text": text, "user_name": user_name, "team_id": team_id}).encode()
    timestamp = str(int(time.time()))
    signature = _slack_signature(str(settings.SLACK_SIGNING_SECRET), timestamp, body)
    return await client.post(
        "/api/v1/slack/commands",
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": signature,
        },
    )


@pytest.fixture(autouse=True)
def _secure_slack_defaults(monkeypatch):
    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", "test-slack-signing-secret")
    monkeypatch.setattr(slack_commands, "_resolve_org_id_for_team", AsyncMock(return_value=1))


@pytest.mark.asyncio
async def test_slack_help_command(client):
    r = await _post_slack_command(client, text="help")
    assert r.status_code == 200
    data = r.json()
    assert "text" in data
    assert "Nidin BOS" in data["text"]
    assert data["response_type"] == "ephemeral"


@pytest.mark.asyncio
async def test_slack_empty_command_shows_help(client):
    r = await _post_slack_command(client, text="")
    assert r.status_code == 200
    assert "help" in r.json()["text"].lower()


@pytest.mark.asyncio
async def test_slack_status_command(client):
    r = await _post_slack_command(client, text="status")
    assert r.status_code == 200
    data = r.json()
    assert "System Status" in data["text"]
    assert "Integrations connected" in data["text"]
    assert "Open tasks" in data["text"]


@pytest.mark.asyncio
async def test_slack_tasks_command(client):
    r = await _post_slack_command(client, text="tasks")
    assert r.status_code == 200
    assert "Open Tasks" in r.json()["text"]


@pytest.mark.asyncio
async def test_slack_approvals_command(client):
    r = await _post_slack_command(client, text="approvals")
    assert r.status_code == 200
    assert "Pending Approvals" in r.json()["text"]


@pytest.mark.asyncio
async def test_slack_briefing_command(client):
    r = await _post_slack_command(client, text="briefing")
    assert r.status_code == 200
    data = r.json()
    assert "Briefing" in data["text"]
    assert "Open tasks" in data["text"]


@pytest.mark.asyncio
async def test_slack_unknown_command(client):
    r = await _post_slack_command(client, text="foobar")
    assert r.status_code == 200
    assert "Unknown command" in r.json()["text"]


@pytest.mark.asyncio
async def test_slack_commands_fail_closed_when_secret_missing(client, monkeypatch):
    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", None)
    r = await client.post("/api/v1/slack/commands", data={"text": "help", "user_name": "nidin"})
    assert r.status_code == 503
