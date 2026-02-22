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
