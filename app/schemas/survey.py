"""Survey definition and response schemas for CRM."""


from pydantic import BaseModel, Field


class SurveyDefinitionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    questions_json: str = Field("[]", max_length=100_000)
    is_active: bool = True


class SurveyDefinitionUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    questions_json: str | None = None
    is_active: bool | None = None


class SurveyResponseCreate(BaseModel):
    survey_id: int
    contact_id: int | None = None
    score: int = Field(0, ge=0, le=100)
    nps_score: int | None = Field(None, ge=0, le=10)
    answers_json: str = Field("{}", max_length=50_000)
    feedback: str | None = None
