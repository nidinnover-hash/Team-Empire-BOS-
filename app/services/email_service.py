"""
Email service - business logic for Gmail sync, AI summarization, and reply drafting.

Flow:
  1. sync_emails()      -> pull from Gmail, store in DB
  2. summarize_email()  -> AI summarizes the email body
  3. draft_reply()      -> AI drafts a reply, creates Gmail draft + approval request
  4. send_approved_reply() -> ONLY after approval is granted, sends via Gmail
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.logs.audit import record_action
from app.models.approval import Approval
from app.models.email import Email
from app.services.ai_router import call_ai
from app.schemas.approval import ApprovalRequestCreate
from app.services.approval import request_approval
from app.services.integration import connect_integration, get_integration_by_type, mark_sync_time
from app.tools import gmail as gmail_tool

logger = logging.getLogger(__name__)

# Per-org lock to serialize concurrent OAuth token refreshes
_refresh_locks: dict[int, asyncio.Lock] = {}


def _get_refresh_lock(org_id: int) -> asyncio.Lock:
    return _refresh_locks.setdefault(org_id, asyncio.Lock())

# Prefixes that indicate call_ai() returned an error string instead of content
_AI_ERROR_PREFIXES = ("Error:", "error:", "I'm sorry", "I cannot", "I'm unable")


class EmailSyncError(Exception):
    """Raised when Gmail sync fails for an external/integration reason."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _classify_gmail_error(error_text: str) -> str:
    """Map upstream Gmail error text to stable internal error codes."""
    text = error_text.lower()
    if "accessnotconfigured" in text or "has not been used in project" in text:
        return "gmail_api_disabled"
    if "invalid_grant" in text or "invalid credentials" in text:
        return "gmail_reconnect_required"
    return "gmail_upstream_error"


def _get_tokens(integration) -> tuple[str, str | None, str | None]:
    """Extract access_token, refresh_token, expires_at from integration config."""
    cfg = integration.config_json or {}
    invalid = cfg.get("__invalid_token_fields")
    if isinstance(invalid, list) and invalid:
        return ("", None, cfg.get("expires_at"))
    return (
        cfg.get("access_token", ""),
        cfg.get("refresh_token"),
        cfg.get("expires_at"),
    )


def _is_ai_error(text: str | None) -> bool:
    """Return True if text looks like an AI router error string."""
    if not text or not text.strip():
        return True
    return any(text.startswith(prefix) for prefix in _AI_ERROR_PREFIXES)


def _build_fallback_reply(subject: str | None, instruction: str) -> str:
    """
    Generate a safe deterministic fallback reply when AI providers are unavailable.
    Keeps operations draft-only workflows resilient during quota/outage windows.
    """
    topic = (subject or "your message").strip()
    extra = instruction.strip()
    lines = [
        "Hi,",
        "",
        f"Thanks for your email about {topic}.",
        "We received it and will review the details shortly.",
    ]
    if extra:
        lines.append(f"Current note: {extra}")
    lines.extend(
        [
            "I'll share a clear next-step update as soon as possible.",
            "",
            "Best,",
            "Nidin",
        ]
    )
    return "\n".join(lines)


async def _persist_refreshed_tokens(
    db: AsyncSession,
    org_id: int,
    integration,
    refreshed_tokens: dict,
    old_refresh_token: str | None,
) -> None:
    """Persist a refreshed access_token back to the integrations table."""
    cfg = dict(integration.config_json or {})
    cfg["access_token"] = refreshed_tokens["access_token"]
    if refreshed_tokens.get("expires_at"):
        cfg["expires_at"] = refreshed_tokens["expires_at"]
    # Keep the existing refresh_token (Google only returns it on first consent)
    if old_refresh_token and not cfg.get("refresh_token"):
        cfg["refresh_token"] = old_refresh_token
    try:
        await connect_integration(
            db=db,
            organization_id=org_id,
            integration_type="gmail",
            config_json=cfg,
        )
    except Exception as exc:
        logger.error("Failed to persist refreshed Gmail tokens for org %d: %s", org_id, type(exc).__name__)


# -- Sync --------------------------------------------------------------------

async def sync_emails(
    db: AsyncSession,
    org_id: int,
    actor_user_id: int,
) -> int:
    """
    Fetch recent emails from Gmail and store new ones in DB.
    Deduplicates by (gmail_id, organization_id) - org-scoped to prevent
    cross-tenant collision on shared gmail_id values.
    Returns count of new emails stored.
    """
    if not settings.FEATURE_EMAIL_SYNC:
        return 0
    integration = await get_integration_by_type(db, org_id, "gmail")
    if not integration:
        return 0

    access_token, refresh_token, expires_at = _get_tokens(integration)
    if not access_token:
        # Stored token payload is unusable (missing/corrupted/old encryption key).
        # Mark integration disconnected so UI reflects the real state.
        if integration.status != "disconnected":
            integration.status = "disconnected"
            await db.commit()
        raise EmailSyncError(
            code="gmail_reconnect_required",
            message=(
                "Gmail tokens are missing or corrupted (possibly encrypted with an old key). "
                "Reconnect Gmail on the Integrations page."
            ),
        )
    try:
        raw_emails, refreshed_tokens = await asyncio.to_thread(
            gmail_tool.fetch_recent_emails,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            max_results=20,
        )
    except Exception as exc:
        code = _classify_gmail_error(str(exc))
        message_by_code = {
            "gmail_api_disabled": (
                "Gmail API is disabled for this Google Cloud project. "
                "Enable gmail.googleapis.com and retry."
            ),
            "gmail_reconnect_required": (
                "Gmail authentication expired or was revoked. "
                "Reconnect Gmail and try again."
            ),
            "gmail_upstream_error": (
                "Gmail sync failed due to an upstream API error. "
                "Try again, then reconnect Gmail if needed."
            ),
        }
        raise EmailSyncError(code=code, message=message_by_code[code]) from exc

    # Persist refreshed tokens if auto-refresh occurred (serialized per-org)
    if refreshed_tokens:
        async with _get_refresh_lock(org_id):
            await _persist_refreshed_tokens(db, org_id, integration, refreshed_tokens, refresh_token)

    # Batch dedup: single query for all gmail_ids
    incoming_ids = [raw["gmail_id"] for raw in raw_emails if raw.get("gmail_id")]
    existing_ids: set[str] = set()
    if incoming_ids:
        existing_q = await db.execute(
            select(Email.gmail_id).where(
                Email.gmail_id.in_(incoming_ids),
                Email.organization_id == org_id,
            )
        )
        existing_ids = {row.gmail_id for row in existing_q}

    new_count = 0
    for raw in raw_emails:
        try:
            gmail_id = raw.get("gmail_id")
            if not gmail_id or gmail_id in existing_ids:
                continue

            received_at = None
            if raw.get("received_at"):
                try:
                    received_at = datetime.fromisoformat(raw["received_at"])
                except ValueError:
                    pass

            email = Email(
                organization_id=org_id,
                gmail_id=gmail_id,
                thread_id=raw.get("thread_id"),
                from_address=raw.get("from_address"),
                to_address=raw.get("to_address"),
                subject=raw.get("subject"),
                body_text=raw.get("body_text"),
                received_at=received_at,
                created_at=datetime.now(timezone.utc),
            )
            db.add(email)
            existing_ids.add(gmail_id)
            new_count += 1
        except Exception as exc:
            logger.warning(
                "Skipping email %s during sync (org %s): %s",
                raw.get("gmail_id", "?"),
                org_id,
                exc,
            )
            continue

    if new_count:
        await db.commit()
        await mark_sync_time(db, integration)
        await record_action(
            db=db,
            event_type="email_sync",
            actor_user_id=actor_user_id,
            entity_type="email",
            entity_id=None,
            payload_json={"new_emails": new_count},
            organization_id=org_id,
        )

    return new_count


async def check_gmail_health(
    db: AsyncSession,
    org_id: int,
) -> dict:
    """
    Validate Gmail integration credentials by reading Gmail profile.
    Returns a health payload with status and optional diagnostics.
    """
    integration = await get_integration_by_type(db, org_id, "gmail")
    if not integration:
        return {"status": "not_connected"}

    access_token, refresh_token, expires_at = _get_tokens(integration)
    if not access_token:
        return {"status": "misconfigured", "code": "missing_access_token"}

    try:
        profile, refreshed_tokens = await asyncio.to_thread(
            gmail_tool.get_profile,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )
    except Exception as exc:
        return {"status": "error", "code": _classify_gmail_error(str(exc))}

    if refreshed_tokens:
        async with _get_refresh_lock(org_id):
            await _persist_refreshed_tokens(db, org_id, integration, refreshed_tokens, refresh_token)

    return {
        "status": "ok",
        "email_address": profile.get("emailAddress"),
        "messages_total": profile.get("messagesTotal"),
        "threads_total": profile.get("threadsTotal"),
    }


# -- List --------------------------------------------------------------------

async def list_emails(
    db: AsyncSession,
    org_id: int,
    limit: int = 50,
    offset: int = 0,
    unread_only: bool = False,
) -> list[Email]:
    query = (
        select(Email)
        .where(Email.organization_id == org_id)
        .order_by(Email.received_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if unread_only:
        query = query.where(Email.is_read.is_(False))
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_email(db: AsyncSession, email_id: int, org_id: int) -> Email | None:
    result = await db.execute(
        select(Email).where(Email.id == email_id, Email.organization_id == org_id)
    )
    return cast(Email | None, result.scalar_one_or_none())


# -- AI Summarize -------------------------------------------------------------

async def summarize_email(
    db: AsyncSession,
    email_id: int,
    org_id: int,
    actor_user_id: int,
) -> str | None:
    """AI summarizes the email body. Saves result to DB."""
    email = await get_email(db, email_id, org_id)
    if not email or not email.body_text:
        return None

    summary = await call_ai(
        system_prompt=(
            "You are an email assistant. Summarize the following email in 2-3 bullet points. "
            "Be concise. Focus on: what is being asked, who sent it, and what action is needed."
        ),
        user_message=(
            f"From: {email.from_address or 'Unknown'}\n"
            f"Subject: {email.subject or '(no subject)'}\n\n"
            f"{email.body_text}"
        ),
        provider=settings.EMAIL_AI_PROVIDER or settings.DEFAULT_AI_PROVIDER,
        organization_id=org_id,
    )

    email.ai_summary = summary
    # Only mark read if AI produced a real summary (not an error placeholder)
    if not _is_ai_error(summary):
        email.is_read = True
    await db.commit()
    await db.refresh(email)

    await record_action(
        db=db,
        event_type="email_summarized",
        actor_user_id=actor_user_id,
        entity_type="email",
        entity_id=email_id,
        payload_json={"subject": email.subject},
        organization_id=org_id,
    )
    return summary


# -- AI Draft Reply -----------------------------------------------------------

async def draft_reply(
    db: AsyncSession,
    email_id: int,
    org_id: int,
    actor_user_id: int,
    instruction: str = "",
) -> str | None:
    """
    AI drafts a reply to the email.
    Creates a Gmail API draft (stores gmail_draft_id) and an approval request
    (stores approval_id on the email row). Nothing is sent without approval.
    Returns the draft text, or None if AI failed or email not found.
    """
    email = await get_email(db, email_id, org_id)
    if not email or not email.body_text:
        return None

    user_prompt = (
        f"From: {email.from_address}\n"
        f"Subject: {email.subject}\n\n"
        f"Email body:\n{email.body_text}"
    )
    if instruction:
        user_prompt += f"\n\nInstruction for reply: {instruction}"

    draft = await call_ai(
        system_prompt=(
            "You are Nidin's email assistant. Draft a professional, concise reply to this email. "
            "Write as if you are Nidin. Do not add placeholder text like [Your Name] - "
            "sign off as Nidin. Keep it short and direct."
        ),
        user_message=user_prompt,
        provider=settings.EMAIL_AI_PROVIDER or settings.DEFAULT_AI_PROVIDER,
        max_tokens=600,
        organization_id=org_id,
    )

    # Degrade gracefully during provider outage/rate-limit by creating a
    # deterministic fallback draft instead of dropping the workflow.
    if _is_ai_error(draft):
        draft = _build_fallback_reply(email.subject, instruction)

    # Create Gmail API draft for preview in Gmail UI
    integration = await get_integration_by_type(db, org_id, "gmail")
    gmail_draft_id: str | None = None
    if integration:
        access_token, refresh_token, expires_at = _get_tokens(integration)
        try:
            gmail_draft_id = await asyncio.to_thread(
                gmail_tool.create_draft,
                access_token=access_token,
                to=email.from_address or "",
                subject=f"Re: {email.subject or ''}",
                body=draft,
                refresh_token=refresh_token,
                expires_at=expires_at,
            )
        except Exception as exc:
            logger.warning("Gmail draft creation failed for email %d: %s", email_id, type(exc).__name__)

    # Create approval request first so we have its ID
    approval = await request_approval(
        db=db,
        requested_by=actor_user_id,
        data=ApprovalRequestCreate(
            organization_id=org_id,
            approval_type="send_message",
            payload_json={
                "email_id": email_id,
                "to": email.from_address,
                "subject": f"Re: {email.subject}",
                "draft_preview": (draft or "")[:300],
            },
        ),
    )

    # Persist draft text, Gmail draft ID, and approval FK on email row
    email.draft_reply = draft
    email.gmail_draft_id = gmail_draft_id
    email.approval_id = approval.id
    email.reply_approved = False
    await db.commit()

    await record_action(
        db=db,
        event_type="email_draft_created",
        actor_user_id=actor_user_id,
        entity_type="email",
        entity_id=email_id,
        payload_json={
            "subject": email.subject,
            "to": email.from_address,
            "gmail_draft_id": gmail_draft_id,
            "approval_id": approval.id,
        },
        organization_id=org_id,
    )
    return draft


# -- AI Strategize ------------------------------------------------------------

async def strategize_email(
    db: AsyncSession,
    email_id: int,
    org_id: int,
    actor_user_id: int,
) -> str | None:
    """
    ChatGPT provides a strategic analysis of the email:
    business impact, what the sender really wants, recommended action, and tone.
    """
    email = await get_email(db, email_id, org_id)
    if not email:
        raise ValueError("Email not found")
    if not email.body_text:
        raise ValueError("Email has no body to analyze")

    analysis = await call_ai(
        system_prompt=(
            "You are Nidin's strategic advisor. Analyze this email and provide:\n"
            "1. SITUATION: What is actually happening here (1-2 sentences)\n"
            "2. WHAT THEY WANT: The real ask behind the email\n"
            "3. BUSINESS IMPACT: Risk or opportunity this represents\n"
            "4. RECOMMENDED ACTION: Exactly what Nidin should do and when\n"
            "5. TONE GUIDE: How to respond (firm/warm/neutral/urgent)\n\n"
            "Be direct. No fluff."
        ),
        user_message=(
            f"From: {email.from_address or 'Unknown'}\n"
            f"Subject: {email.subject or '(no subject)'}\n\n"
            f"{email.body_text}"
        ),
        provider=settings.EMAIL_AI_PROVIDER or settings.DEFAULT_AI_PROVIDER,
        max_tokens=700,
        organization_id=org_id,
    )

    if _is_ai_error(analysis):
        raise RuntimeError("Strategy generation failed (AI provider unavailable or misconfigured)")

    await record_action(
        db=db,
        event_type="email_strategized",
        actor_user_id=actor_user_id,
        entity_type="email",
        entity_id=email_id,
        payload_json={"subject": email.subject},
        organization_id=org_id,
    )
    return analysis


# -- AI Compose New Email -----------------------------------------------------

async def compose_email(
    db: AsyncSession,
    org_id: int,
    actor_user_id: int,
    to: str,
    subject: str,
    instruction: str,
) -> str | None:
    """
    ChatGPT drafts a brand-new email (not a reply) from Nidin.
    Creates a Gmail draft + approval request. Nothing sends without approval.
    Returns the draft text, or None on failure.
    """
    draft = await call_ai(
        system_prompt=(
            "You are Nidin's email assistant. Write a complete, professional email from Nidin. "
            "Do not use placeholder text. Sign off as Nidin. "
            "Write a proper subject line if not provided. Be clear and direct."
        ),
        user_message=(
            f"To: {to}\n"
            f"Subject: {subject}\n\n"
            f"Instructions: {instruction}"
        ),
        provider=settings.EMAIL_AI_PROVIDER or settings.DEFAULT_AI_PROVIDER,
        max_tokens=600,
        organization_id=org_id,
    )

    if _is_ai_error(draft):
        return None

    # Create Gmail draft
    integration = await get_integration_by_type(db, org_id, "gmail")
    gmail_draft_id: str | None = None
    if integration:
        access_token, refresh_token, expires_at = _get_tokens(integration)
        try:
            gmail_draft_id = await asyncio.to_thread(
                gmail_tool.create_draft,
                access_token=access_token,
                to=to,
                subject=subject,
                body=draft,
                refresh_token=refresh_token,
                expires_at=expires_at,
            )
        except Exception as exc:
            logger.warning("Gmail draft creation failed for compose to %s: %s", to, type(exc).__name__)

    # Require approval before anything can be sent
    approval = await request_approval(
        db=db,
        requested_by=actor_user_id,
        data=ApprovalRequestCreate(
            organization_id=org_id,
            approval_type="send_message",
            payload_json={
                "compose": True,
                "to": to,
                "subject": subject,
                "draft_body": draft,
                "draft_preview": (draft or "")[:300],
                "gmail_draft_id": gmail_draft_id,
            },
        ),
    )

    await record_action(
        db=db,
        event_type="email_composed",
        actor_user_id=actor_user_id,
        entity_type="email",
        entity_id=None,
        payload_json={"to": to, "subject": subject, "approval_id": approval.id},
        organization_id=org_id,
    )
    return draft


# -- Send Approved Reply ------------------------------------------------------

async def send_approved_compose(
    db: AsyncSession,
    approval: Approval,
    org_id: int,
    actor_user_id: int,
) -> bool:
    """
    Send a composed email from a send_message approval payload (no email_id row).
    Uses approval.executed_at as the idempotency guard.
    """
    payload = approval.payload_json or {}
    to = payload.get("to")
    subject = payload.get("subject") or ""
    draft_body = payload.get("draft_body")

    async def _record_send_blocked(reason: str) -> None:
        await record_action(
            db=db,
            event_type="email_send_blocked",
            actor_user_id=actor_user_id,
            entity_type="email",
            entity_id=None,
            payload_json={"reason": reason, "approval_id": approval.id},
            organization_id=org_id,
        )

    if approval.organization_id != org_id or approval.status != "approved":
        await _record_send_blocked("approval_not_approved_or_wrong_org")
        return False
    if not to or not draft_body:
        await _record_send_blocked("missing_compose_payload")
        return False

    # Atomic claim — only proceeds if executed_at is still NULL
    _claim_ts = datetime.now(timezone.utc)
    _claim_result = await db.execute(
        update(Approval)
        .where(Approval.id == approval.id, Approval.executed_at.is_(None))
        .values(executed_at=_claim_ts)
    )
    await db.commit()
    if _claim_result.rowcount == 0:
        await _record_send_blocked("approval_already_executed")
        return False

    integration = await get_integration_by_type(db, org_id, "gmail")
    if not integration:
        # Atomic rollback — only release if our claim_ts still matches
        await db.execute(
            update(Approval)
            .where(Approval.id == approval.id, Approval.executed_at == _claim_ts)
            .values(executed_at=None)
        )
        await db.commit()
        await _record_send_blocked("gmail_not_connected")
        return False

    access_token, refresh_token, expires_at = _get_tokens(integration)
    sent = cast(bool, await asyncio.to_thread(
        gmail_tool.send_email,
        access_token=access_token,
        to=str(to),
        subject=str(subject),
        body=str(draft_body),
        refresh_token=refresh_token,
        expires_at=expires_at,
    ))
    if not sent:
        logger.warning("Gmail compose-send failed — rolled back approval %d", approval.id)
        await db.execute(
            update(Approval)
            .where(Approval.id == approval.id, Approval.executed_at == _claim_ts)
            .values(executed_at=None)
        )
        await db.commit()
        await _record_send_blocked("gmail_send_failed")
        return False

    await record_action(
        db=db,
        event_type="email_sent",
        actor_user_id=actor_user_id,
        entity_type="email",
        entity_id=None,
        payload_json={
            "to": str(to),
            "subject": str(subject),
            "compose": True,
            "approval_id": approval.id,
        },
        organization_id=org_id,
    )
    return True


async def send_approved_reply(
    db: AsyncSession,
    email_id: int,
    org_id: int,
    actor_user_id: int,
) -> bool:
    """
    Send the drafted reply - ONLY if the linked approval is approved and unused.

    Guard order:
    1. Email exists, has a draft, and has not been sent yet
    2. email.approval_id FK resolves to an approved Approval in the same org
    3. approval.executed_at IS NULL (idempotency guard - prevents double-send)
    4. Mark executed_at = now() BEFORE sending (claim the send slot)
    5. Send via Gmail; rollback executed_at on failure
    6. Clear gmail_draft_id after send (draft consumed, reference now stale)

    Returns True on success.
    """
    async def _record_send_blocked(reason: str, approval_id: int | None = None) -> None:
        await record_action(
            db=db,
            event_type="email_send_blocked",
            actor_user_id=actor_user_id,
            entity_type="email",
            entity_id=email_id,
            payload_json={"reason": reason, "approval_id": approval_id},
            organization_id=org_id,
        )

    email = await get_email(db, email_id, org_id)
    if not email or not email.draft_reply:
        await _record_send_blocked("missing_email_or_draft")
        return False

    if email.reply_sent:
        await _record_send_blocked("already_sent", approval_id=email.approval_id)
        return False  # Already sent

    if not email.approval_id:
        await _record_send_blocked("missing_approval_link")
        return False  # No approval linked - draft_reply() was not called

    # Resolve approval via FK - single query, org-scoped
    approval_result = await db.execute(
        select(Approval).where(
            Approval.id == email.approval_id,
            Approval.organization_id == org_id,
            Approval.status == "approved",
        )
    )
    approval = approval_result.scalar_one_or_none()
    if approval is None:
        await _record_send_blocked("approval_not_approved_or_missing", approval_id=email.approval_id)
        return False

    # Defense-in-depth: linked approval payload must match this email.
    payload_email_id = (approval.payload_json or {}).get("email_id")
    if payload_email_id != email_id:
        await _record_send_blocked("approval_email_id_mismatch", approval_id=approval.id)
        return False

    # Claim the send slot with an atomic UPDATE WHERE executed_at IS NULL.
    # Two concurrent requests could both pass a read-then-check; this ensures
    # only the first one proceeds (rowcount == 0 means someone else got there first).
    _claim_ts = datetime.now(timezone.utc)
    _claim_result = await db.execute(
        update(Approval)
        .where(Approval.id == approval.id, Approval.executed_at.is_(None))
        .values(executed_at=_claim_ts)
    )
    await db.commit()
    if _claim_result.rowcount == 0:
        await _record_send_blocked("approval_already_executed", approval_id=approval.id)
        return False

    # Get Gmail tokens
    integration = await get_integration_by_type(db, org_id, "gmail")
    if not integration:
        # Atomic rollback — only release if our claim_ts still matches
        await db.execute(
            update(Approval)
            .where(Approval.id == approval.id, Approval.executed_at == _claim_ts)
            .values(executed_at=None)
        )
        await db.commit()
        await _record_send_blocked("gmail_not_connected", approval_id=approval.id)
        return False

    access_token, refresh_token, expires_at = _get_tokens(integration)
    sent = await asyncio.to_thread(
        gmail_tool.send_email,
        access_token=access_token,
        to=email.from_address or "",
        subject=f"Re: {email.subject or ''}",
        body=email.draft_reply,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )

    if sent:
        email.reply_sent = True
        email.reply_approved = True
        # Clear gmail_draft_id - draft was consumed and is now stale
        email.gmail_draft_id = None
        await db.commit()
        await record_action(
            db=db,
            event_type="email_sent",
            actor_user_id=actor_user_id,
            entity_type="email",
            entity_id=email_id,
            payload_json={"to": email.from_address, "subject": email.subject},
            organization_id=org_id,
        )
    else:
        # Gmail send failed — atomic rollback so only our claim is released
        logger.warning("Gmail send failed for email %d — rolled back approval %d", email_id, approval.id)
        await db.execute(
            update(Approval)
            .where(Approval.id == approval.id, Approval.executed_at == _claim_ts)
            .values(executed_at=None)
        )
        await db.commit()
        await _record_send_blocked("gmail_send_failed", approval_id=approval.id)

    return sent
