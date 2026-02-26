from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from app.core.config import settings
from app.core.oauth_state import sign_oauth_state, verify_oauth_state
from app.core.privacy import sanitize_response_payload
from app.schemas.integration import IntegrationRead

GENERIC_CONNECT_ALLOWED_TYPES = {"gmail", "google_calendar", "whatsapp_business"}
GENERIC_CONNECT_BLOCKED_ROUTES = {
    "github": "/api/v1/integrations/github/connect",
    "clickup": "/api/v1/integrations/clickup/connect",
    "digitalocean": "/api/v1/integrations/digitalocean/connect",
    "slack": "/api/v1/integrations/slack/connect",
    "perplexity": "/api/v1/integrations/perplexity/connect",
    "linkedin": "/api/v1/integrations/linkedin/connect",
    "notion": "/api/v1/integrations/notion/connect",
    "stripe": "/api/v1/integrations/stripe/connect",
    "google_analytics": "/api/v1/integrations/google-analytics/connect",
    "calendly": "/api/v1/integrations/calendly/connect",
    "elevenlabs": "/api/v1/integrations/elevenlabs/connect",
    "hubspot": "/api/v1/integrations/hubspot/connect",
    "ai_openai": "/api/v1/integrations/ai/openai/connect",
    "ai_anthropic": "/api/v1/integrations/ai/anthropic/connect",
    "ai_groq": "/api/v1/integrations/ai/groq/connect",
    "ai_gemini": "/api/v1/integrations/ai/gemini/connect",
}

INTEGRATION_SETUP_SPECS: list[tuple[str, str, str, str, str]] = [
    (
        "github",
        "GitHub",
        "/api/v1/integrations/github/connect",
        "/api/v1/integrations/github/status",
        "/api/v1/integrations/github/sync",
    ),
    (
        "clickup",
        "ClickUp",
        "/api/v1/integrations/clickup/connect",
        "/api/v1/integrations/clickup/status",
        "/api/v1/integrations/clickup/sync",
    ),
    (
        "digitalocean",
        "DigitalOcean",
        "/api/v1/integrations/digitalocean/connect",
        "/api/v1/integrations/digitalocean/status",
        "/api/v1/integrations/digitalocean/sync",
    ),
    (
        "slack",
        "Slack",
        "/api/v1/integrations/slack/connect",
        "/api/v1/integrations/slack/status",
        "/api/v1/integrations/slack/sync",
    ),
    (
        "perplexity",
        "Perplexity AI",
        "/api/v1/integrations/perplexity/connect",
        "/api/v1/integrations/perplexity/status",
        "/api/v1/integrations/perplexity/search",
    ),
    (
        "linkedin",
        "LinkedIn",
        "/api/v1/integrations/linkedin/connect",
        "/api/v1/integrations/linkedin/status",
        "/api/v1/integrations/linkedin/publish",
    ),
    (
        "notion",
        "Notion",
        "/api/v1/integrations/notion/connect",
        "/api/v1/integrations/notion/status",
        "/api/v1/integrations/notion/sync",
    ),
    (
        "stripe",
        "Stripe",
        "/api/v1/integrations/stripe/connect",
        "/api/v1/integrations/stripe/status",
        "/api/v1/integrations/stripe/sync",
    ),
    (
        "google_analytics",
        "Google Analytics",
        "/api/v1/integrations/google-analytics/connect",
        "/api/v1/integrations/google-analytics/status",
        "/api/v1/integrations/google-analytics/sync",
    ),
    (
        "calendly",
        "Calendly",
        "/api/v1/integrations/calendly/connect",
        "/api/v1/integrations/calendly/status",
        "/api/v1/integrations/calendly/sync",
    ),
    (
        "elevenlabs",
        "ElevenLabs",
        "/api/v1/integrations/elevenlabs/connect",
        "/api/v1/integrations/elevenlabs/status",
        "/api/v1/integrations/elevenlabs/tts",
    ),
    (
        "hubspot",
        "HubSpot CRM",
        "/api/v1/integrations/hubspot/connect",
        "/api/v1/integrations/hubspot/status",
        "/api/v1/integrations/hubspot/sync",
    ),
]


def safe_provider_error(prefix: str) -> str:
    return f"{prefix}. Reconnect integration and retry."


def sign_google_calendar_state(org_id: int) -> str:
    return str(sign_oauth_state(org_id))


def verify_google_calendar_state(
    state: str,
    expected_org_id: int,
    max_age_seconds: int = 600,
) -> None:
    verify_oauth_state(
        state,
        namespace="gcal_oauth",
        max_age_seconds=max_age_seconds,
        expected_org_id=expected_org_id,
    )


def redact_integration(item: IntegrationRead | object) -> IntegrationRead:
    data = IntegrationRead.model_validate(item).model_dump()
    data["config_json"] = sanitize_response_payload(dict(data["config_json"]))
    return IntegrationRead(**data)


def calendar_redirect_uri() -> str:
    direct = (settings.GOOGLE_CALENDAR_REDIRECT_URI or "").strip()
    if direct:
        return direct

    # Backward-compatible fallback: derive calendar callback from GOOGLE_REDIRECT_URI host/scheme.
    gmail_redirect = (settings.GOOGLE_REDIRECT_URI or "").strip()
    if not gmail_redirect:
        return ""

    parsed = urlsplit(gmail_redirect)
    if not parsed.scheme or not parsed.netloc:
        return ""

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            "/api/v1/integrations/google-calendar/oauth/callback",
            "",
            "",
        )
    )
