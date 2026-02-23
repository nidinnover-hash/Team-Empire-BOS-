import asyncio
import hmac
import secrets
from hashlib import sha256
from time import time
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.idempotency import (
    IdempotencyConflictError,
    build_fingerprint,
    get_cached_response,
    store_response,
)
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.email import ComposeRequest, DraftReplyRequest, EmailRead, SyncResult
from app.services import email_service
from app.services.email_service import EmailSyncError
from app.tools.gmail import exchange_code_for_tokens, get_gmail_auth_url
from app.services.integration import connect_integration, get_integration_by_type

router = APIRouter(prefix="/email", tags=["Email"])

# Per-org compose rate limit: max N composes per rolling window
_compose_counts: dict[int, list[float]] = {}
_COMPOSE_MAX_PER_HOUR = 20
_COMPOSE_WINDOW = 3600  # 1 hour


def _check_compose_rate(org_id: int) -> None:
    """Raise 429 if the org has exceeded the compose rate limit."""
    now = time()
    bucket = _compose_counts.setdefault(org_id, [])
    _compose_counts[org_id] = [t for t in bucket if now - t < _COMPOSE_WINDOW]
    if len(_compose_counts[org_id]) >= _COMPOSE_MAX_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=f"Compose rate limit: max {_COMPOSE_MAX_PER_HOUR} per hour.",
        )
    _compose_counts[org_id].append(now)


def _oauth_error_detail(error_code: str) -> str:
    if error_code == "token_exchange_failed":
        return "OAuth failed: token exchange failed. Reconnect and try again."
    return "OAuth failed: provider rejected the authorization code. Reconnect and try again."


def _sign_email_state(org_id: int) -> str:
    ts = int(time())
    nonce = secrets.token_urlsafe(16)
    payload = f"{org_id}:{ts}:{nonce}"
    sig = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        sha256,
    ).hexdigest()
    return f"{payload}:{sig}"


def _verify_email_state(state: str, max_age_seconds: int = 600) -> int:
    try:
        parts = state.split(":", 3)
        if len(parts) != 4:
            raise ValueError("Invalid state format")
        org_id_str, ts_str, nonce, sig = parts
        payload = f"{org_id_str}:{ts_str}:{nonce}"
        expected = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            payload.encode("utf-8"),
            sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("Invalid state signature")
        ts = int(ts_str)
        if int(time()) - ts > max_age_seconds:
            raise ValueError("State expired")
        return int(org_id_str)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state") from exc


@router.get("/auth-url")
async def gmail_auth_url(
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """
    Get the Gmail OAuth URL. Visit this URL in your browser to connect Gmail.
    After login, Google redirects to your GOOGLE_REDIRECT_URI with a code.
    """
    org_id = int(user.get("org_id", 1))
    state = _sign_email_state(org_id)
    url = get_gmail_auth_url(state=state)
    return {"auth_url": url, "state": state}


@router.get("/callback")
async def gmail_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Handle Gmail OAuth callback. Exchange code for tokens and save to DB.
    Google redirects here after the user grants permission.
    """
    org_id = _verify_email_state(state)
    tokens = await asyncio.to_thread(exchange_code_for_tokens, code)
    if "error" in tokens:
        error_code = str(tokens.get("error") or "unknown")
        raise HTTPException(status_code=400, detail=_oauth_error_detail(error_code))

    existing = await get_integration_by_type(db, org_id, "gmail")
    existing_cfg = existing.config_json if existing else {}
    refresh_token = tokens.get("refresh_token") or existing_cfg.get("refresh_token")

    # Store tokens in integrations table — never in logs or responses
    await connect_integration(
        db=db,
        organization_id=org_id,
        integration_type="gmail",
        config_json={
            "access_token": tokens["access_token"],
            "refresh_token": refresh_token,
            "expires_at": tokens.get("expires_at"),
        },
    )

    return {"status": "connected", "message": "Gmail connected successfully"}


@router.post("/sync", response_model=SyncResult)
async def sync_emails(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SyncResult:
    """Sync recent emails from Gmail into the database."""
    org_id = int(current_user.get("org_id", 1))
    scope = f"email_sync:{org_id}"
    fingerprint = build_fingerprint({"org_id": org_id, "action": "sync"})
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return cast(SyncResult, SyncResult.model_validate(cached))
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        new_count = await email_service.sync_emails(
            db=db,
            org_id=org_id,
            actor_user_id=int(current_user["id"]),
        )
    except EmailSyncError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Email sync failed [{exc.code}]: {exc.message}",
        ) from exc
    response = SyncResult(
        new_emails=new_count,
        message=f"Synced {new_count} new email(s) from Gmail.",
    )
    if idempotency_key:
        store_response(scope, idempotency_key, response.model_dump(), fingerprint=fingerprint)
    return response


@router.get("/health")
async def gmail_health(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Return Gmail integration health for the current org."""
    org_id = int(current_user.get("org_id", 1))
    return cast(dict[str, Any], await email_service.check_gmail_health(db=db, org_id=org_id))


@router.get("/inbox", response_model=list[EmailRead])
async def list_inbox(
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[EmailRead]:
    """List emails from the inbox. Filter by unread if needed."""
    org_id = int(_user.get("org_id", 1))
    return cast(
        list[EmailRead],
        await email_service.list_emails(
            db, org_id=org_id, limit=limit, offset=offset, unread_only=unread_only
        ),
    )


@router.post("/{email_id}/summarize")
async def summarize_email(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """AI summarizes the email in 2-3 bullet points."""
    org_id = int(current_user.get("org_id", 1))
    summary = await email_service.summarize_email(
        db=db,
        email_id=email_id,
        org_id=org_id,
        actor_user_id=int(current_user["id"]),
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="Email not found or has no body")
    return {"email_id": email_id, "summary": summary}


@router.post("/{email_id}/draft-reply")
async def draft_reply(
    email_id: int,
    body: DraftReplyRequest = DraftReplyRequest(),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """
    AI drafts a reply to this email.
    Creates an approval request — nothing is sent until you approve.
    """
    org_id = int(current_user.get("org_id", 1))
    scope = f"email_draft_reply:{org_id}:{email_id}"
    fingerprint = build_fingerprint(
        {"org_id": org_id, "email_id": email_id, "instruction": body.instruction or ""}
    )
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return cast(dict[str, Any], cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    draft = await email_service.draft_reply(
        db=db,
        email_id=email_id,
        org_id=org_id,
        actor_user_id=int(current_user["id"]),
        instruction=body.instruction,
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Email not found or has no body")
    response: dict[str, Any] = {
        "email_id": email_id,
        "draft": draft,
        "status": "pending_approval",
        "message": "Draft created. Go to /api/v1/approvals to review and approve before sending.",
    }
    if idempotency_key:
        store_response(scope, idempotency_key, response, fingerprint=fingerprint)
    return response


@router.post("/{email_id}/send")
async def send_email(
    email_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """
    Send the drafted reply.
    ONLY works if an approved approval exists for this email.
    CEO and ADMIN only.
    """
    org_id = int(current_user.get("org_id", 1))
    scope = f"email_send:{org_id}:{email_id}"
    fingerprint = build_fingerprint({"org_id": org_id, "email_id": email_id, "action": "send"})
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return cast(dict[str, Any], cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    sent = await email_service.send_approved_reply(
        db=db,
        email_id=email_id,
        org_id=org_id,
        actor_user_id=int(current_user["id"]),
    )
    if not sent:
        # Approving with "YES EXECUTE" can already dispatch send_message.
        # Treat repeat /send calls as idempotent success if email is already sent.
        existing = await email_service.get_email(db, email_id=email_id, org_id=org_id)
        if existing and existing.reply_sent:
            response = {
                "email_id": email_id,
                "status": "already_sent",
                "message": "Email was already sent previously.",
            }
            if idempotency_key:
                store_response(scope, idempotency_key, response, fingerprint=fingerprint)
            return response
        raise HTTPException(
            status_code=409,
            detail="Cannot send. Either no approved approval exists, email already sent, or Gmail not connected.",
        )
    response = {"email_id": email_id, "status": "sent", "message": "Email sent successfully."}
    if idempotency_key:
        store_response(scope, idempotency_key, response, fingerprint=fingerprint)
    return response


@router.post("/{email_id}/strategize")
async def strategize_email(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """
    ChatGPT strategic analysis: situation, what they want, business impact,
    recommended action, and tone guide. No approval needed — read-only analysis.
    """
    org_id = int(current_user.get("org_id", 1))
    try:
        analysis = await email_service.strategize_email(
            db=db,
            email_id=email_id,
            org_id=org_id,
            actor_user_id=int(current_user["id"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"email_id": email_id, "strategy": analysis}


@router.post("/compose")
async def compose_email(
    body: ComposeRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """
    ChatGPT drafts a brand-new email from Nidin.
    Creates an approval request — nothing sends until you approve it.
    """
    org_id = int(current_user.get("org_id", 1))
    _check_compose_rate(org_id)
    scope = f"email_compose:{org_id}"
    fingerprint = build_fingerprint(
        {
            "org_id": org_id,
            "to": body.to,
            "subject": body.subject,
            "instruction": body.instruction,
        }
    )
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return cast(dict[str, Any], cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    draft = await email_service.compose_email(
        db=db,
        org_id=org_id,
        actor_user_id=int(current_user["id"]),
        to=body.to,
        subject=body.subject,
        instruction=body.instruction,
    )
    if draft is None:
        raise HTTPException(status_code=502, detail="AI failed to generate draft. Check OpenAI key.")
    response: dict[str, Any] = {
        "to": body.to,
        "subject": body.subject,
        "draft": draft,
        "status": "pending_approval",
        "message": "Draft composed. Go to /api/v1/approvals to review and approve before sending.",
    }
    if idempotency_key:
        store_response(scope, idempotency_key, response, fingerprint=fingerprint)
    return response
