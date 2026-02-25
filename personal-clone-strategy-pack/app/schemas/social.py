from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SocialPlatform = Literal["instagram", "facebook", "linkedin", "youtube", "x", "tiktok", "audible", "other"]
SocialPostStatus = Literal["draft", "queued", "approved", "published", "failed"]
SocialContentMode = Literal["social_media", "entertainment"]

SOCIAL_MEDIA_PLATFORMS = {"instagram", "facebook", "linkedin", "x", "tiktok", "other"}
ENTERTAINMENT_PLATFORMS = {"youtube", "audible"}


class SocialPostCreate(BaseModel):
    content_mode: SocialContentMode = "social_media"
    platform: SocialPlatform
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=10_000)
    scheduled_for: datetime | None = None
    media_url: str | None = Field(None, max_length=1024)

    @model_validator(mode="after")
    def validate_mode_platform(self) -> "SocialPostCreate":
        if self.content_mode == "social_media" and self.platform not in SOCIAL_MEDIA_PLATFORMS:
            raise ValueError("social_media mode supports only instagram/facebook/linkedin/x/tiktok/other")
        if self.content_mode == "entertainment" and self.platform not in ENTERTAINMENT_PLATFORMS:
            raise ValueError("entertainment mode supports only youtube/audible")
        return self


class SocialPostStatusUpdate(BaseModel):
    status: SocialPostStatus


class SocialPostRead(BaseModel):
    id: int
    organization_id: int
    content_mode: SocialContentMode
    platform: SocialPlatform
    title: str
    content: str
    status: SocialPostStatus
    scheduled_for: datetime | None
    media_url: str | None
    created_by_user_id: int | None
    approved_by_user_id: int | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SocialSummaryRead(BaseModel):
    total_posts: int
    draft: int
    queued: int
    approved: int
    published: int
    failed: int
