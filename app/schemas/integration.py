from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

IntegrationType = Literal[
    "gmail", "google_calendar", "github", "clickup",
    "slack", "whatsapp_business", "digitalocean",
    "perplexity", "linkedin", "notion", "stripe",
    "google_analytics", "calendly", "elevenlabs", "hubspot",
]
IntegrationStatus = Literal["connected", "disconnected", "error"]
IntegrationTestStatus = Literal["ok", "failed", "not_configured"]

_SENSITIVE_CONFIG_KEYS = frozenset({
    "access_token", "refresh_token", "api_key", "bot_token",
    "app_secret", "api_token", "private_key",
})


class IntegrationConnectRequest(BaseModel):
    type: IntegrationType = Field(...)
    config_json: dict = Field(default_factory=dict)


class IntegrationRead(BaseModel):
    id: int
    organization_id: int
    type: IntegrationType
    config_json: dict
    status: IntegrationStatus
    last_sync_at: datetime | None
    last_sync_status: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _redact_tokens(self):
        if self.config_json:
            self.config_json = {
                k: ("***" if k in _SENSITIVE_CONFIG_KEYS else v)
                for k, v in self.config_json.items()
            }
        return self


class IntegrationTestResult(BaseModel):
    integration_id: int
    status: IntegrationTestStatus
    message: str


class GoogleAuthUrlRead(BaseModel):
    auth_url: str
    state: str


class GoogleOAuthCallbackRequest(BaseModel):
    code: str = Field(..., max_length=2000)
    state: str = Field(..., max_length=1000)
    calendar_id: str = Field("primary", max_length=200)


class CalendarSyncResult(BaseModel):
    date: str
    synced: int


class CalendarEventRead(BaseModel):
    id: int
    date: str
    content: str
    location: str | None = None


class AIProviderStatus(BaseModel):
    provider: str
    configured: bool
    active: bool
    email_active: bool = False
    model: str


class AITestResult(BaseModel):
    provider: str
    status: IntegrationTestStatus
    message: str
    sample_response: str | None = None


class CodingProjectDiscoveryRead(BaseModel):
    provider_options: list[str]
    questions: list[str]
    next_prompt: str


class WhatsAppWebhookResult(BaseModel):
    status: str = "received"
    entries: int = 0
    stored: int = 0


class WhatsAppSendRequest(BaseModel):
    to: str = Field(..., min_length=5, max_length=30)
    body: str = Field(..., min_length=1, max_length=4096)


class WhatsAppSendResult(BaseModel):
    status: str
    to: str
    message_id: str | None = None


class ClickUpConnectRequest(BaseModel):
    api_token: str = Field(..., min_length=2, max_length=200)


class ClickUpSyncResult(BaseModel):
    synced: int
    last_sync_at: str | None = None


class ClickUpStatusRead(BaseModel):
    connected: bool
    last_sync_at: str | None = None
    username: str | None = None
    team_id: str | None = None


class GitHubConnectRequest(BaseModel):
    api_token: str = Field(..., min_length=2, max_length=200)


class GitHubSyncResult(BaseModel):
    prs_synced: int
    issues_synced: int
    last_sync_at: str | None = None


class GitHubStatusRead(BaseModel):
    connected: bool
    last_sync_at: str | None = None
    login: str | None = None
    repos_tracked: int | None = None


class SlackConnectRequest(BaseModel):
    bot_token: str = Field(..., min_length=1, max_length=200)


class SlackSyncResult(BaseModel):
    channels_synced: int
    messages_read: int
    last_sync_at: str | None = None


class SlackStatusRead(BaseModel):
    connected: bool
    last_sync_at: str | None = None
    team: str | None = None
    channels_tracked: int | None = None


class SlackSendRequest(BaseModel):
    channel_id: str = Field(..., min_length=1, max_length=100)
    text: str = Field(..., min_length=1, max_length=4000)


class GitHubInstallationDiscoveryResult(BaseModel):
    ok: bool
    org: str
    installation_id: int


class DigitalOceanConnectRequest(BaseModel):
    api_token: str = Field(..., min_length=2, max_length=300)


class DigitalOceanStatusRead(BaseModel):
    connected: bool
    last_sync_at: str | None = None


class DigitalOceanSyncResult(BaseModel):
    droplets: int
    members: int
    error: str | None = None


class IntegrationSetupItem(BaseModel):
    key: str
    label: str
    connected: bool
    connect_endpoint: str
    status_endpoint: str
    sync_endpoint: str
    next_step: str


class IntegrationSetupGuideRead(BaseModel):
    generated_at: datetime
    ready_count: int
    total_count: int
    items: list[IntegrationSetupItem]


# ── Perplexity (web search) ─────────────────────────────────────────────

class PerplexityConnectRequest(BaseModel):
    api_key: str = Field(..., min_length=2, max_length=300)


class PerplexityStatusRead(BaseModel):
    connected: bool
    last_sync_at: str | None = None


class PerplexitySearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    max_tokens: int = Field(default=1024, ge=100, le=4096)


class PerplexitySearchResult(BaseModel):
    content: str
    citations: list[str]


# ── LinkedIn ────────────────────────────────────────────────────────────

class LinkedInConnectRequest(BaseModel):
    access_token: str = Field(..., min_length=2, max_length=2000)


class LinkedInStatusRead(BaseModel):
    connected: bool
    last_sync_at: str | None = None
    name: str | None = None
    author_urn: str | None = None


class LinkedInPublishRequest(BaseModel):
    text: str = Field(..., min_length=5, max_length=3000)
    visibility: str = Field(default="PUBLIC", pattern="^(PUBLIC|CONNECTIONS)$")


class LinkedInPublishResult(BaseModel):
    post_id: str
    status: str


# ── Notion ──────────────────────────────────────────────────────────────

class NotionConnectRequest(BaseModel):
    api_token: str = Field(..., min_length=2, max_length=300)


class NotionStatusRead(BaseModel):
    connected: bool
    last_sync_at: str | None = None
    bot_name: str | None = None


class NotionSyncResult(BaseModel):
    pages_synced: int
    notes_created: int
    last_sync_at: str | None = None


class NotionSearchRequest(BaseModel):
    query: str = Field(default="", max_length=200)
    page_size: int = Field(default=20, ge=1, le=100)


# ── Stripe ──────────────────────────────────────────────────────────────

class StripeConnectRequest(BaseModel):
    secret_key: str = Field(..., min_length=2, max_length=300)


class StripeStatusRead(BaseModel):
    connected: bool
    last_sync_at: str | None = None


class StripeSyncResult(BaseModel):
    charges_synced: int
    refunds_synced: int
    disputes_synced: int
    last_sync_at: str | None = None


# ── Google Analytics ────────────────────────────────────────────────────

class GoogleAnalyticsStatusRead(BaseModel):
    connected: bool
    property_id: str | None = None
    last_sync_at: str | None = None


class GoogleAnalyticsSyncResult(BaseModel):
    sessions_30d: int
    active_users_30d: int
    page_views_30d: int
    top_pages: list[dict[str, str]]
    traffic_sources: list[dict[str, str]]


# ── Calendly ────────────────────────────────────────────────────────────

class CalendlyConnectRequest(BaseModel):
    api_token: str = Field(..., min_length=2, max_length=300)


class CalendlyStatusRead(BaseModel):
    connected: bool
    last_sync_at: str | None = None
    user_name: str | None = None


class CalendlySyncResult(BaseModel):
    events_synced: int
    upcoming_events: int
    last_sync_at: str | None = None


# ── ElevenLabs ──────────────────────────────────────────────────────────

class ElevenLabsConnectRequest(BaseModel):
    api_key: str = Field(..., min_length=2, max_length=300)


class ElevenLabsStatusRead(BaseModel):
    connected: bool
    last_sync_at: str | None = None
    voices_available: int = 0
    characters_used: int = 0
    character_limit: int = 0


class ElevenLabsTTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: str | None = Field(default=None, max_length=100)


class ElevenLabsTTSResult(BaseModel):
    audio_size_bytes: int
    voice_id: str
    model: str


# ── HubSpot ─────────────────────────────────────────────────────────────

class HubSpotConnectRequest(BaseModel):
    access_token: str = Field(..., min_length=2, max_length=300)


class HubSpotStatusRead(BaseModel):
    connected: bool
    last_sync_at: str | None = None


class HubSpotSyncResult(BaseModel):
    contacts_synced: int
    deals_synced: int
    last_sync_at: str | None = None
