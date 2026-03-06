from pydantic import BaseModel, Field

from app.schemas.contact import QualificationStatus, RoutingStatus


class BulkLeadRouteRequest(BaseModel):
    contact_ids: list[int] = Field(..., min_length=1, max_length=200)
    lead_type: str | None = None
    routed_company_id: int | None = Field(None, ge=1)
    routing_reason: str | None = Field(None, max_length=500)


class BulkLeadQualifyRequest(BaseModel):
    contact_ids: list[int] = Field(..., min_length=1, max_length=200)
    qualified_score: int | None = Field(None, ge=0, le=100)
    qualified_status: QualificationStatus | None = None
    qualification_notes: str | None = Field(None, max_length=4000)
    routing_status: RoutingStatus | None = None
    lead_type: str | None = None


class BulkLeadActionResult(BaseModel):
    requested: int
    updated: int
    skipped: int
    updated_contact_ids: list[int]


class EmpireSlaConfigRead(BaseModel):
    stale_unrouted_days: int = Field(3, ge=1, le=30)
    warning_stale_count: int = Field(3, ge=1, le=5000)
    warning_unrouted_count: int = Field(8, ge=1, le=5000)


class EmpireSlaConfigUpdate(BaseModel):
    stale_unrouted_days: int = Field(3, ge=1, le=30)
    warning_stale_count: int = Field(3, ge=1, le=5000)
    warning_unrouted_count: int = Field(8, ge=1, le=5000)


class EscalateStaleLeadsRequest(BaseModel):
    contact_ids: list[int] | None = None
    limit: int = Field(20, ge=1, le=200)


class EscalateStaleLeadsResult(BaseModel):
    considered: int
    escalated: int
    decision_card_ids: list[int]
