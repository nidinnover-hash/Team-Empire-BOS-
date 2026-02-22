"""
Gmail OAuth tool — all Gmail API calls live here.

Rules:
- This file only talks to Gmail. No DB logic here.
- send_email() must NEVER be called directly from endpoints.
  It is only called from email_service.send_approved_reply()
  after an approval record is confirmed.
- Tokens are never logged or returned in API responses.
"""

import base64
import email as email_lib
from datetime import datetime, timezone

from app.core.config import settings

# Gmail scope — modify allows read + send + label
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def get_gmail_auth_url(state: str | None = None) -> str:
    """
    Build the Google OAuth URL for Gmail access.
    User visits this URL, logs in, and Google sends back a code.
    """
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        client_config={
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        },
        scopes=GMAIL_SCOPES,
    )
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # forces refresh_token to be returned
        state=state,
    )
    return auth_url


def exchange_code_for_tokens(code: str) -> dict:
    """
    Exchange the OAuth callback code for access + refresh tokens.

    Returns:
        {
          "access_token": "...",
          "refresh_token": "...",
          "expires_at": "2026-02-21T12:00:00+00:00"
        }
    Never raises — returns {"error": "..."} on failure.
    """
    try:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
                }
            },
            scopes=GMAIL_SCOPES,
        )
        flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
        flow.fetch_token(code=code)
        creds = flow.credentials
        return {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expires_at": creds.expiry.isoformat() if creds.expiry else None,
        }
    except Exception as e:
        return {"error": str(e)}


def _build_gmail_service(access_token: str, refresh_token: str | None = None):
    """Build an authenticated Gmail API service object."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=GMAIL_SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _extract_body(payload: dict) -> str:
    """Extract plain text body from a Gmail message payload."""
    body = ""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    elif "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                    break
    return body.strip()


def _get_header(headers: list[dict], name: str) -> str | None:
    """Get a header value from Gmail message headers."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def fetch_recent_emails(
    access_token: str,
    refresh_token: str | None = None,
    max_results: int = 20,
) -> list[dict]:
    """
    Fetch recent emails from Gmail inbox.

    Returns list of dicts:
    {
        gmail_id, thread_id, from_address, to_address,
        subject, body_text, received_at
    }
    Returns empty list on any error.
    """
    try:
        service = _build_gmail_service(access_token, refresh_token)
        result = service.users().messages().list(
            userId="me",
            maxResults=max_results,
            labelIds=["INBOX"],
        ).execute()

        messages = result.get("messages", [])
        emails = []

        for msg in messages:
            detail = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="full",
            ).execute()

            headers = detail.get("payload", {}).get("headers", [])
            internal_date = detail.get("internalDate")
            received_at = None
            if internal_date:
                ts = int(internal_date) / 1000
                received_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

            emails.append({
                "gmail_id": detail["id"],
                "thread_id": detail.get("threadId"),
                "from_address": _get_header(headers, "From"),
                "to_address": _get_header(headers, "To"),
                "subject": _get_header(headers, "Subject"),
                "body_text": _extract_body(detail.get("payload", {})),
                "received_at": received_at,
            })

        return emails
    except Exception:
        return []


def create_draft(
    access_token: str,
    to: str,
    subject: str,
    body: str,
    refresh_token: str | None = None,
) -> str | None:
    """
    Create a Gmail draft via the API.

    Returns the Gmail draft ID (string) on success, or None on failure.

    IMPORTANT: Only called from email_service.draft_reply(). Never from endpoints.
    The draft ID is stored in Email.gmail_draft_id for idempotency.
    """
    try:
        service = _build_gmail_service(access_token, refresh_token)
        raw_message = email_lib.message.EmailMessage()
        raw_message["To"] = to
        raw_message["Subject"] = subject
        raw_message.set_content(body)
        encoded = base64.urlsafe_b64encode(raw_message.as_bytes()).decode()
        result = service.users().drafts().create(
            userId="me",
            body={"message": {"raw": encoded}},
        ).execute()
        return result.get("id")
    except Exception:
        return None


def send_email(
    access_token: str,
    to: str,
    subject: str,
    body: str,
    refresh_token: str | None = None,
) -> bool:
    """
    Send an email via Gmail API.

    IMPORTANT: This function must ONLY be called from
    email_service.send_approved_reply() after approval is confirmed.
    Never call this directly from an endpoint.

    Returns True on success, False on failure.
    """
    try:
        service = _build_gmail_service(access_token, refresh_token)

        raw_message = email_lib.message.EmailMessage()
        raw_message["To"] = to
        raw_message["Subject"] = subject
        raw_message.set_content(body)

        encoded = base64.urlsafe_b64encode(raw_message.as_bytes()).decode()
        service.users().messages().send(
            userId="me",
            body={"raw": encoded},
        ).execute()
        return True
    except Exception:
        return False
