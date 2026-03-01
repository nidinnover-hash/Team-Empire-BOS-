"""Slack slash command interface — interact with BOS from Slack.

Handles /bos commands:
  /bos status       — system health summary
  /bos tasks        — pending task count
  /bos approvals    — pending approval count
  /bos briefing     — today's executive summary (non-AI, fast)
  /bos help         — list available commands
"""

from __future__ import annotations

import hmac
import logging
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.logs.audit import record_action
from app.models.approval import Approval
from app.models.integration import Integration
from app.models.task import Task

router = APIRouter(prefix="/slack", tags=["Slack Commands"])
logger = logging.getLogger(__name__)

_DEFAULT_ORG_ID = 1


def _verify_slack_signature(request_body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack request signature using signing secret."""
    signing_secret = getattr(settings, "SLACK_SIGNING_SECRET", None)
    if not signing_secret:
        return False
    sig_basestring = f"v0:{timestamp}:{request_body.decode()}"
    computed = "v0=" + hmac.new(
        signing_secret.encode(), sig_basestring.encode(), sha256
    ).hexdigest()
    return hmac.compare_digest(computed, signature)


@router.post("/commands")
async def handle_slack_command(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Handle Slack slash commands (/bos <subcommand>)."""
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    signing_secret = getattr(settings, "SLACK_SIGNING_SECRET", None)
    if signing_secret and not _verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    form = await request.form()
    command_text = str(form.get("text", "")).strip().lower()
    user_name = str(form.get("user_name", "unknown"))

    org_id = _DEFAULT_ORG_ID

    await record_action(
        db,
        event_type="slack_command_received",
        actor_user_id=None,
        organization_id=org_id,
        entity_type="slack",
        entity_id=None,
        payload_json={"command": command_text, "user": user_name},
    )

    if command_text in ("", "help"):
        return _slack_response(_help_text())
    elif command_text == "status":
        return await _handle_status(db, org_id)
    elif command_text == "tasks":
        return await _handle_tasks(db, org_id)
    elif command_text == "approvals":
        return await _handle_approvals(db, org_id)
    elif command_text == "briefing":
        return await _handle_briefing(db, org_id)
    else:
        return _slack_response(f"Unknown command: `{command_text}`\n\n{_help_text()}")


def _slack_response(text: str, in_channel: bool = False) -> dict:
    return {
        "response_type": "in_channel" if in_channel else "ephemeral",
        "text": text,
    }


def _help_text() -> str:
    return (
        "*Nidin BOS — Slack Commands*\n"
        "`/bos status` — System health overview\n"
        "`/bos tasks` — Pending tasks count\n"
        "`/bos approvals` — Pending approvals\n"
        "`/bos briefing` — Today's executive snapshot\n"
        "`/bos help` — This help message"
    )


async def _handle_status(db: AsyncSession, org_id: int) -> dict:
    integrations = (
        await db.execute(
            select(func.count(Integration.id)).where(
                Integration.organization_id == org_id,
                Integration.status == "connected",
            )
        )
    ).scalar_one()
    tasks_open = (
        await db.execute(
            select(func.count(Task.id)).where(
                Task.organization_id == org_id,
                Task.is_done.is_(False),
            )
        )
    ).scalar_one()
    pending = (
        await db.execute(
            select(func.count(Approval.id)).where(
                Approval.organization_id == org_id,
                Approval.status == "pending",
            )
        )
    ).scalar_one()
    return _slack_response(
        f"*System Status*\n"
        f"Integrations connected: {integrations}\n"
        f"Open tasks: {tasks_open}\n"
        f"Pending approvals: {pending}"
    )


async def _handle_tasks(db: AsyncSession, org_id: int) -> dict:
    count = (
        await db.execute(
            select(func.count(Task.id)).where(
                Task.organization_id == org_id,
                Task.is_done.is_(False),
            )
        )
    ).scalar_one()
    return _slack_response(f"*Open Tasks:* {count}")


async def _handle_approvals(db: AsyncSession, org_id: int) -> dict:
    count = (
        await db.execute(
            select(func.count(Approval.id)).where(
                Approval.organization_id == org_id,
                Approval.status == "pending",
            )
        )
    ).scalar_one()
    return _slack_response(f"*Pending Approvals:* {count}")


async def _handle_briefing(db: AsyncSession, org_id: int) -> dict:
    tasks_open = (
        await db.execute(
            select(func.count(Task.id)).where(
                Task.organization_id == org_id,
                Task.is_done.is_(False),
            )
        )
    ).scalar_one()
    pending = (
        await db.execute(
            select(func.count(Approval.id)).where(
                Approval.organization_id == org_id,
                Approval.status == "pending",
            )
        )
    ).scalar_one()
    integrations = (
        await db.execute(
            select(func.count(Integration.id)).where(
                Integration.organization_id == org_id,
                Integration.status == "connected",
            )
        )
    ).scalar_one()
    return _slack_response(
        f"*Today's Briefing*\n"
        f"Open tasks: {tasks_open}\n"
        f"Pending approvals: {pending}\n"
        f"Connected integrations: {integrations}\n"
        f"_Use the dashboard for a full AI-generated briefing._"
    )
