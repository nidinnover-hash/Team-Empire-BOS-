"""
Typed structures for Integration.config_json per integration type.

These TypedDicts document exactly which keys are stored in the encrypted
config_json column for each integration. They are used for type-safe access
in service code and serve as living documentation of each config shape.

Usage:
    from app.schemas.integration_configs import GmailConfig
    cfg = GmailConfig(**integration.decrypt_config())
"""
from __future__ import annotations

from typing import TypedDict


class GmailConfig(TypedDict, total=False):
    """OAuth tokens for Gmail integration (stored encrypted)."""
    access_token: str
    refresh_token: str
    token_expiry: str        # ISO-8601 datetime string
    email: str               # authenticated Gmail address


class GoogleCalendarConfig(TypedDict, total=False):
    """OAuth tokens for Google Calendar integration (stored encrypted)."""
    access_token: str
    refresh_token: str
    token_expiry: str        # ISO-8601 datetime string


class ClickUpConfig(TypedDict, total=False):
    """Personal Access Token config for ClickUp integration."""
    api_key: str             # ClickUp PAT (pk_...)
    team_id: str             # ClickUp workspace/team ID
    login: str               # ClickUp user email (informational)


class GitHubConfig(TypedDict, total=False):
    """GitHub App/PAT config for GitHub integration."""
    api_key: str             # GitHub PAT or installation token
    org: str                 # GitHub organization name


class SlackConfig(TypedDict, total=False):
    """Bot Token config for Slack integration."""
    api_key: str             # xoxb- bot token
    team_id: str             # Slack workspace ID
    team_name: str           # Slack workspace name (informational)


class WhatsAppConfig(TypedDict, total=False):
    """WhatsApp Business API config."""
    phone_number_id: str     # Meta Business phone number ID
    access_token: str        # Meta Graph API token
    webhook_verify_token: str


class NotionConfig(TypedDict, total=False):
    """Notion integration config."""
    api_key: str             # Notion integration token (secret_...)


class StripeConfig(TypedDict, total=False):
    """Stripe integration config."""
    api_key: str             # Stripe secret key (sk_live_... or sk_test_...)


class HubSpotConfig(TypedDict, total=False):
    """HubSpot integration config."""
    access_token: str        # HubSpot private app token


class DigitalOceanConfig(TypedDict, total=False):
    """DigitalOcean integration config."""
    api_key: str             # DO personal access token


class LinkedInConfig(TypedDict, total=False):
    """LinkedIn OAuth integration config."""
    access_token: str
    refresh_token: str
    token_expiry: str        # ISO-8601 datetime string
    person_urn: str          # LinkedIn person URN for posting


class PerplexityConfig(TypedDict, total=False):
    """Perplexity AI integration config."""
    api_key: str


class ElevenLabsConfig(TypedDict, total=False):
    """ElevenLabs TTS integration config."""
    api_key: str
    default_voice_id: str


class GA4Config(TypedDict, total=False):
    """Google Analytics 4 integration config."""
    api_key: str             # Service account JSON or GA4 API key
    property_id: str         # GA4 property ID


class CalendlyConfig(TypedDict, total=False):
    """Calendly integration config."""
    api_key: str             # Calendly personal access token


# Map of integration type → config TypedDict class for runtime lookup
INTEGRATION_CONFIG_TYPES: dict[str, type] = {
    "gmail": GmailConfig,
    "google_calendar": GoogleCalendarConfig,
    "clickup": ClickUpConfig,
    "github": GitHubConfig,
    "slack": SlackConfig,
    "whatsapp": WhatsAppConfig,
    "notion": NotionConfig,
    "stripe": StripeConfig,
    "hubspot": HubSpotConfig,
    "digitalocean": DigitalOceanConfig,
    "linkedin": LinkedInConfig,
    "perplexity": PerplexityConfig,
    "elevenlabs": ElevenLabsConfig,
    "google_analytics": GA4Config,
    "calendly": CalendlyConfig,
}
