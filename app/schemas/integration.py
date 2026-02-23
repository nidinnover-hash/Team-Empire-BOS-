from datetime import datetime

from pydantic import BaseModel, Field


class IntegrationConnectRequest(BaseModel):
    type: str = Field(..., max_length=50)
    config_json: dict = Field(default_factory=dict)


class IntegrationRead(BaseModel):
    id: int
    organization_id: int
    type: str
    config_json: dict
    status: str
    last_sync_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IntegrationTestResult(BaseModel):
    integration_id: int
    status: str
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
    model: str


class AITestResult(BaseModel):
    provider: str
    status: str
    message: str
    sample_response: str | None = None


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
