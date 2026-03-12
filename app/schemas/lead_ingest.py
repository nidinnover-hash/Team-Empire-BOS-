"""Schemas for lead ingest APIs (e.g. social)."""

from pydantic import BaseModel, Field


class SocialLeadIngestRequest(BaseModel):
    """Single lead from a social platform (FB, IG, LinkedIn, etc.)."""

    source_platform: str = Field(..., min_length=1, max_length=80, description="e.g. facebook, instagram, linkedin")
    page_id: str | None = Field(None, max_length=120)
    brand_slug: str | None = Field(None, max_length=80)
    full_name: str = Field(..., min_length=1, max_length=500)
    email: str | None = Field(None, max_length=500)
    phone: str | None = Field(None, max_length=50)
    message: str | None = Field(None, max_length=5000)
    lead_type: str = Field("general", max_length=50)
    region: str | None = Field(None, max_length=80)
    utm: dict | None = None
    raw_payload: dict | None = None


class SocialLeadIngestResponse(BaseModel):
    """Result of ingesting a social lead."""

    contact_id: int
    created: bool
    routed: bool
    owner_user_id: int | None = None
    sla_deadline_utc: str | None = None
