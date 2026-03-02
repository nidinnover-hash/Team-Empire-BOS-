"""Tests for the Slack command interface."""

import pytest


@pytest.mark.asyncio
async def test_slack_help_command(client):
    r = await client.post("/api/v1/slack/commands", data={"text": "help", "user_name": "nidin"})
    assert r.status_code == 200
    data = r.json()
    assert "text" in data
    assert "Nidin BOS" in data["text"]
    assert data["response_type"] == "ephemeral"


@pytest.mark.asyncio
async def test_slack_empty_command_shows_help(client):
    r = await client.post("/api/v1/slack/commands", data={"text": "", "user_name": "nidin"})
    assert r.status_code == 200
    assert "help" in r.json()["text"].lower()


@pytest.mark.asyncio
async def test_slack_status_command(client):
    r = await client.post("/api/v1/slack/commands", data={"text": "status", "user_name": "nidin"})
    assert r.status_code == 200
    data = r.json()
    assert "System Status" in data["text"]
    assert "Integrations connected" in data["text"]
    assert "Open tasks" in data["text"]


@pytest.mark.asyncio
async def test_slack_tasks_command(client):
    r = await client.post("/api/v1/slack/commands", data={"text": "tasks", "user_name": "nidin"})
    assert r.status_code == 200
    assert "Open Tasks" in r.json()["text"]


@pytest.mark.asyncio
async def test_slack_approvals_command(client):
    r = await client.post("/api/v1/slack/commands", data={"text": "approvals", "user_name": "nidin"})
    assert r.status_code == 200
    assert "Pending Approvals" in r.json()["text"]


@pytest.mark.asyncio
async def test_slack_briefing_command(client):
    r = await client.post("/api/v1/slack/commands", data={"text": "briefing", "user_name": "nidin"})
    assert r.status_code == 200
    data = r.json()
    assert "Briefing" in data["text"]
    assert "Open tasks" in data["text"]


@pytest.mark.asyncio
async def test_slack_unknown_command(client):
    r = await client.post("/api/v1/slack/commands", data={"text": "foobar", "user_name": "nidin"})
    assert r.status_code == 200
    assert "Unknown command" in r.json()["text"]
