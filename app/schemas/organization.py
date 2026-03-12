from datetime import datetime

from pydantic import BaseModel, Field

# Industry/sector types for multi-business (Tech, Recruitment, Study Abroad, Sales & Marketing).
INDUSTRY_TYPES = ("tech", "recruitment", "study_abroad", "marketing")


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100)
    parent_organization_id: int | None = Field(None, ge=1)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    branch_label: str | None = Field(None, max_length=120)
    industry_type: str | None = Field(None, max_length=50)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    slug: str | None = Field(None, max_length=100)
    parent_organization_id: int | None = Field(None, ge=1)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    branch_label: str | None = Field(None, max_length=120)
    industry_type: str | None = Field(None, max_length=50)
    expected_config_version: int | None = Field(None, ge=1)


class OrganizationRead(BaseModel):
    id: int
    parent_organization_id: int | None
    name: str
    slug: str
    country_code: str | None
    branch_label: str | None
    industry_type: str | None
    config_version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeatureFlagValue(BaseModel):
    enabled: bool = True
    rollout_percentage: int = Field(100, ge=0, le=100)


class OrganizationFeatureFlagsRead(BaseModel):
    config_version: int
    flags: dict[str, FeatureFlagValue]


class OrganizationFeatureFlagsUpdate(BaseModel):
    expected_config_version: int | None = Field(None, ge=1)
    flags: dict[str, FeatureFlagValue]
