from datetime import datetime

from pydantic import BaseModel, Field


class IntegrationConnectRequest(BaseModel):
    type: str
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
    code: str
    state: str
    calendar_id: str = "primary"


class CalendarSyncResult(BaseModel):
    date: str
    synced: int


class CalendarEventRead(BaseModel):
    id: int
    date: str
    content: str
    location: str | None = None


class AIProviderStatus(BaseModel):
    provider: str          # "openai" or "anthropic"
    configured: bool       # key is present and not a placeholder
    active: bool           # this is the DEFAULT_AI_PROVIDER
    model: str             # model that will be used


class AITestResult(BaseModel):
    provider: str
    status: str            # "ok" | "failed" | "not_configured"
    message: str
    sample_response: str | None = None
