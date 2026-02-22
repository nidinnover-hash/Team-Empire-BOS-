"""
Email service — business logic for Gmail sync, AI summarization, and reply drafting.

Flow:
  1. sync_emails()      → pull from Gmail, store in DB
  2. summarize_email()  → AI summarizes the email body
  3. draft_reply()      → AI drafts a reply, creates Gmail draft + approval request
  4. send_approved_reply() → ONLY after approval is granted, sends via Gmail
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logs.audit import record_action
from app.models.approval import Approval
from app.models.email import Email
from app.services.ai_router import call_ai
from app.schemas.approval import ApprovalRequestCreate
from app.services.approval import request_approval
from app.services.integration import get_integration_by_type, mark_sync_time
from app.tools import gmail as gmail_tool

# Prefixes that indicate call_ai() returned an error string instead of content
_AI_ERROR_PREFIXES = ("Error:", "error:", "I'm sorry", "I cannot", "I'm unable")


def _get_tokens(integration) -> tuple[str, str | None]:
    """Extract access and refresh tokens from integration config."""
    cfg = integration.config_json or {}
    return cfg.get("access_token", ""), cfg.get("refresh_token")


def _is_ai_error(text: str | None) -> bool:
    """Return True if text looks like an AI router error string."""
    if not text or not text.strip():
        return True
    return any(text.startswith(prefix) for prefix in _AI_ERROR_PREFIXES)


# ── Sync ──────────────────────────────────────────────────────────────────────

async def sync_emails(
    db: AsyncSession,
    org_id: int,
    actor_user_id: int,
) -> int:
    """
    Fetch recent emails from Gmail and store new ones in DB.
    Deduplicates by (gmail_id, organization_id) — org-scoped to prevent
    cross-tenant collision on shared gmail_id values.
    Returns count of new emails stored.
    """
    integration = await get_integration_by_type(db, org_id, "gmail")
    if not integration:
        return 0

    access_token, refresh_token = _get_tokens(integration)
    raw_emails = gmail_tool.fetch_recent_emails(
        access_token=access_token,
        refresh_token=refresh_token,
        max_results=20,
    )

    new_count = 0
    for raw in raw_emails:
        # Deduplicate by (gmail_id, organization_id) — not just gmail_id
        exists = await db.execute(
            select(Email).where(
                Email.gmail_id == raw["gmail_id"],
                Email.organization_id == org_id,
            )
        )
        if exists.scalar_one_or_none():
            continue

        received_at = None
        if raw.get("received_at"):
            try:
                received_at = datetime.fromisoformat(raw["received_at"])
            except ValueError:
                pass

        email = Email(
            organization_id=org_id,
            gmail_id=raw["gmail_id"],
            thread_id=raw.get("thread_id"),
            from_address=raw.get("from_address"),
            to_address=raw.get("to_address"),
            subject=raw.get("subject"),
            body_text=raw.get("body_text"),
            received_at=received_at,
            created_at=datetime.now(timezone.utc),
        )
        db.add(email)
        new_count += 1

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


# ── List ──────────────────────────────────────────────────────────────────────

async def list_emails(
    db: AsyncSession,
    org_id: int,
    limit: int = 50,
    unread_only: bool = False,
) -> list[Email]:
    query = (
        select(Email)
        .where(Email.organization_id == org_id)
        .order_by(Email.received_at.desc())
        .limit(limit)
    )
    if unread_only:
        query = query.where(Email.is_read == False)  # noqa: E712
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_email(db: AsyncSession, email_id: int, org_id: int) -> Email | None:
    result = await db.execute(
        select(Email).where(Email.id == email_id, Email.organization_id == org_id)
    )
    return result.scalar_one_or_none()


# ── AI Summarize ──────────────────────────────────────────────────────────────

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
        user_message=f"From: {email.from_address}\nSubject: {email.subject}\n\n{email.body_text}",
    )

    email.ai_summary = summary
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


# ── AI Draft Reply ────────────────────────────────────────────────────────────

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
            "Write as if you are Nidin. Do not add placeholder text like [Your Name] — "
            "sign off as Nidin. Keep it short and direct."
        ),
        user_message=user_prompt,
    )

    # Reject AI error strings — don't store them as drafts
    if _is_ai_error(draft):
        return None

    # Create Gmail API draft for preview in Gmail UI
    integration = await get_integration_by_type(db, org_id, "gmail")
    gmail_draft_id: str | None = None
    if integration:
        access_token, refresh_token = _get_tokens(integration)
        gmail_draft_id = gmail_tool.create_draft(
            access_token=access_token,
            to=email.from_address or "",
            subject=f"Re: {email.subject or ''}",
            body=draft,
            refresh_token=refresh_token,
        )

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


# ── Send Approved Reply ───────────────────────────────────────────────────────

async def send_approved_reply(
    db: AsyncSession,
    email_id: int,
    org_id: int,
    actor_user_id: int,
) -> bool:
    """
    Send the drafted reply — ONLY if the linked approval is approved and unused.

    Guard order:
    1. Email exists, has a draft, and has not been sent yet
    2. email.approval_id FK resolves to an approved Approval in the same org
    3. approval.executed_at IS NULL (idempotency guard — prevents double-send)
    4. Mark executed_at = now() BEFORE sending (claim the send slot)
    5. Send via Gmail; rollback executed_at on failure

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
        return False  # No approval linked — draft_reply() was not called

    # Resolve approval via FK — single query, org-scoped
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

    # Idempotency guard — reject if already executed
    if approval.executed_at is not None:
        await _record_send_blocked("approval_already_executed", approval_id=approval.id)
        return False

    # Claim the send slot atomically before touching Gmail
    approval.executed_at = datetime.now(timezone.utc)
    await db.commit()

    # Get Gmail tokens
    integration = await get_integration_by_type(db, org_id, "gmail")
    if not integration:
        # No integration — roll back the executed_at claim
        approval.executed_at = None
        await db.commit()
        await _record_send_blocked("gmail_not_connected", approval_id=approval.id)
        return False

    access_token, refresh_token = _get_tokens(integration)
    sent = gmail_tool.send_email(
        access_token=access_token,
        to=email.from_address or "",
        subject=f"Re: {email.subject or ''}",
        body=email.draft_reply,
        refresh_token=refresh_token,
    )

    if sent:
        email.reply_sent = True
        email.reply_approved = True
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
        # Gmail send failed — release the executed_at slot so a retry is possible
        approval.executed_at = None
        await db.commit()
        await _record_send_blocked("gmail_send_failed", approval_id=approval.id)

    return sent
