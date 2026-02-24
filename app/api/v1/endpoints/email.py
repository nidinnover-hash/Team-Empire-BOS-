import asyncio
import logging
from collections import deque as _deque
from time import time
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Header
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.idempotency import (
    IdempotencyConflictError,
    build_fingerprint,
    get_cached_response,
    store_response,
)
from app.core.oauth_state import sign_oauth_state, verify_oauth_state
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.core.config import settings
from app.schemas.email import (
    ComposeRequest,
    DraftReplyRequest,
    EmailControlRunResponse,
    EmailComposeResponse,
    EmailDraftResponse,
    EmailRead,
    EmailSendResponse,
    EmailStrategyResponse,
    EmailSummaryResponse,
    GmailAuthUrlRead,
    GmailHealthRead,
    ManagerReportTemplateRead,
    PendingActionsDigestDraftRead,
    PendingActionsDigestRead,
    SyncResult,
)
from app.services import email_control, email_service
from app.services.email_service import EmailSyncError
from app.tools.gmail import exchange_code_for_tokens, get_gmail_auth_url
from app.services.integration import connect_integration, get_integration_by_type

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email", tags=["Email"])

# Per-org compose rate limit (configurable via settings)
_compose_counts: dict[int, _deque[float]] = {}
_COMPOSE_MAX_ORGS = 500  # cap to prevent memory leak
_COMPOSE_MAX_PER_HOUR = settings.COMPOSE_MAX_PER_HOUR
_COMPOSE_WINDOW_SECONDS = settings.COMPOSE_WINDOW_SECONDS


@router.get("/control/report-template", response_model=ManagerReportTemplateRead)
async def report_template(
    _user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ManagerReportTemplateRead:
    return ManagerReportTemplateRead(**email_control.manager_report_template())


@router.post("/control/process", response_model=EmailControlRunResponse)
async def process_email_control(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EmailControlRunResponse:
    result = await email_control.process_inbox_controls(
        db,
        org_id=int(user["org_id"]),
        actor_user_id=int(user["id"]),
        limit=limit,
    )
    return EmailControlRunResponse(**result)


@router.get("/control/pending-digest", response_model=PendingActionsDigestRead)
async def pending_actions_digest(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> PendingActionsDigestRead:
    digest = await email_control.build_pending_actions_digest(db, org_id=int(user["org_id"]))
    return PendingActionsDigestRead(**digest)


@router.post("/control/pending-digest/draft", response_model=PendingActionsDigestDraftRead)
async def draft_pending_actions_digest(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> PendingActionsDigestDraftRead:
    drafted = await email_control.draft_pending_actions_digest_email(
        db,
        org_id=int(user["org_id"]),
        actor_user_id=int(user["id"]),
    )
    return PendingActionsDigestDraftRead(**drafted)


def _check_compose_rate(org_id: int) -> None:
    """Raise 429 if the org has exceeded the compose rate limit."""
    max_per_hour = _COMPOSE_MAX_PER_HOUR
    window = _COMPOSE_WINDOW_SECONDS
    now = time()
    # Proactively evict stale orgs on every call (O(n) over small dict)
    stale = [k for k, v in _compose_counts.items() if not v or now - v[-1] > window]
    for k in stale:
        del _compose_counts[k]
    if org_id not in _compose_counts:
        _compose_counts[org_id] = _deque()
    bucket = _compose_counts[org_id]
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= max_per_hour:
        raise HTTPException(
            status_code=429,
            detail=f"Compose rate limit: max {max_per_hour} per hour.",
        )
    bucket.append(now)


def _oauth_error_detail(error_code: str) -> str:
    if error_code == "token_exchange_failed":
        return "OAuth failed: token exchange failed. Reconnect and try again."
    return "OAuth failed: provider rejected the authorization code. Reconnect and try again."


def _sign_email_state(org_id: int) -> str:
    return cast(str, sign_oauth_state(org_id))


def _verify_email_state(state: str, max_age_seconds: int = 600) -> int:
    return cast(
        int,
        verify_oauth_state(state, namespace="gmail_oauth", max_age_seconds=max_age_seconds),
    )


@router.get("/auth-url", response_model=GmailAuthUrlRead)
async def gmail_auth_url(
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GmailAuthUrlRead:
    """
    Get the Gmail OAuth URL. Visit this URL in your browser to connect Gmail.
    After login, Google redirects to your GOOGLE_REDIRECT_URI with a code.
    """
    org_id = int(user["org_id"])
    state = _sign_email_state(org_id)
    url = get_gmail_auth_url(state=state)
    return GmailAuthUrlRead(auth_url=url, state=state)


@router.get("/callback")
async def gmail_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Handle Gmail OAuth callback. Exchange code for tokens and save to DB.
    Google redirects here after the user grants permission.
    """
    org_id = _verify_email_state(state)
    try:
        tokens = await asyncio.wait_for(
            asyncio.to_thread(exchange_code_for_tokens, code),
            timeout=15.0,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Google token exchange timed out. Try again.") from exc
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

    # Redirect browser back to integrations page with success indicator
    return RedirectResponse(url="/web/integrations?gmail=connected", status_code=302)


@router.post("/sync", response_model=SyncResult)
async def sync_emails(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SyncResult:
    """Sync recent emails from Gmail into the database."""
    org_id = int(current_user["org_id"])
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
        logger.warning("Email sync failed org=%d: [%s] %s", org_id, exc.code, exc.message)
        raise HTTPException(
            status_code=502,
            detail="Email sync failed. Check the Integrations page for connection status.",
        ) from exc
    response = SyncResult(
        new_emails=new_count,
        message=f"Synced {new_count} new email(s) from Gmail.",
    )
    if idempotency_key:
        store_response(scope, idempotency_key, response.model_dump(), fingerprint=fingerprint)
    return response


@router.get("/health", response_model=GmailHealthRead)
async def gmail_health(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GmailHealthRead:
    """Return Gmail integration health for the current org."""
    org_id = int(current_user["org_id"])
    payload = cast(dict[str, Any], await email_service.check_gmail_health(db=db, org_id=org_id))
    return cast(GmailHealthRead, GmailHealthRead.model_validate(payload))


@router.get("/inbox", response_model=list[EmailRead])
async def list_inbox(
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[EmailRead]:
    """List emails from the inbox. Filter by unread if needed."""
    org_id = int(_user["org_id"])
    return cast(
        list[EmailRead],
        await email_service.list_emails(
            db, org_id=org_id, limit=limit, offset=offset, unread_only=unread_only
        ),
    )


@router.post("/{email_id}/summarize", response_model=EmailSummaryResponse)
async def summarize_email(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EmailSummaryResponse:
    """AI summarizes the email in 2-3 bullet points."""
    org_id = int(current_user["org_id"])
    summary = await email_service.summarize_email(
        db=db,
        email_id=email_id,
        org_id=org_id,
        actor_user_id=int(current_user["id"]),
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="Email not found or has no body")
    return EmailSummaryResponse(email_id=email_id, summary=summary)


@router.post("/{email_id}/draft-reply", response_model=EmailDraftResponse)
async def draft_reply(
    email_id: int,
    body: DraftReplyRequest = DraftReplyRequest(),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EmailDraftResponse:
    """
    AI drafts a reply to this email.
    Creates an approval request — nothing is sent until you approve.
    """
    org_id = int(current_user["org_id"])
    scope = f"email_draft_reply:{org_id}:{email_id}"
    fingerprint = build_fingerprint(
        {"org_id": org_id, "email_id": email_id, "instruction": body.instruction or ""}
    )
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return cast(EmailDraftResponse, EmailDraftResponse.model_validate(cached))
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
    response = EmailDraftResponse(
        email_id=email_id,
        draft=draft,
        status="pending_approval",
        message="Draft created. Go to /api/v1/approvals to review and approve before sending.",
    )
    if idempotency_key:
        store_response(scope, idempotency_key, response.model_dump(), fingerprint=fingerprint)
    return response


@router.post("/{email_id}/send", response_model=EmailSendResponse)
async def send_email(
    email_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> EmailSendResponse:
    """
    Send the drafted reply.
    ONLY works if an approved approval exists for this email.
    CEO and ADMIN only.
    """
    org_id = int(current_user["org_id"])
    scope = f"email_send:{org_id}:{email_id}"
    fingerprint = build_fingerprint({"org_id": org_id, "email_id": email_id, "action": "send"})
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return cast(EmailSendResponse, EmailSendResponse.model_validate(cached))
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
            response = EmailSendResponse(
                email_id=email_id,
                status="already_sent",
                message="Email was already sent previously.",
            )
            if idempotency_key:
                store_response(scope, idempotency_key, response.model_dump(), fingerprint=fingerprint)
            return response
        raise HTTPException(
            status_code=409,
            detail="Cannot send. Either no approved approval exists, email already sent, or Gmail not connected.",
        )
    response = EmailSendResponse(
        email_id=email_id,
        status="sent",
        message="Email sent successfully.",
    )
    if idempotency_key:
        store_response(scope, idempotency_key, response.model_dump(), fingerprint=fingerprint)
    return response


@router.post("/{email_id}/strategize", response_model=EmailStrategyResponse)
async def strategize_email(
    email_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EmailStrategyResponse:
    """
    ChatGPT strategic analysis: situation, what they want, business impact,
    recommended action, and tone guide. No approval needed — read-only analysis.
    """
    org_id = int(current_user["org_id"])
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
    return EmailStrategyResponse(email_id=email_id, strategy=analysis)


@router.post("/compose", response_model=EmailComposeResponse)
async def compose_email(
    body: ComposeRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EmailComposeResponse:
    """
    ChatGPT drafts a brand-new email from Nidin.
    Creates an approval request — nothing sends until you approve it.
    """
    org_id = int(current_user["org_id"])
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
                return cast(EmailComposeResponse, EmailComposeResponse.model_validate(cached))
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
    response = EmailComposeResponse(
        to=body.to,
        subject=body.subject,
        draft=draft,
        status="pending_approval",
        message="Draft composed. Go to /api/v1/approvals to review and approve before sending.",
    )
    if idempotency_key:
        store_response(scope, idempotency_key, response.model_dump(), fingerprint=fingerprint)
    return response
