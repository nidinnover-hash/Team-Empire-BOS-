"""Contact scoring rules — configurable lead scoring engine."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import scoring_rule as rule_service

router = APIRouter(prefix="/scoring-rules", tags=["Contact Scoring"])


class ScoringRuleCreate(BaseModel):
    name: str = Field(..., max_length=200)
    field: str = Field(..., pattern=r"^(company|role|lead_source|pipeline_stage|source_channel|campaign_name|tags|relationship)$")
    operator: str = Field(..., pattern=r"^(contains|equals|starts_with|not_empty)$")
    value: str = Field("", max_length=500)
    score_delta: int = Field(10, ge=-50, le=50)
    description: str | None = None


class ScoringRuleUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    value: str | None = None
    score_delta: int | None = Field(None, ge=-50, le=50)
    is_active: bool | None = None
    description: str | None = None


class ScoringRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    field: str
    operator: str
    value: str
    score_delta: int
    is_active: bool
    description: str | None = None
    created_at: datetime | None = None


@router.get("", response_model=list[ScoringRuleRead])
async def list_scoring_rules(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[ScoringRuleRead]:
    rules = await rule_service.list_rules(db, organization_id=actor["org_id"], active_only=active_only)
    return [ScoringRuleRead.model_validate(r, from_attributes=True) for r in rules]


@router.post("", response_model=ScoringRuleRead, status_code=201)
async def create_scoring_rule(
    data: ScoringRuleCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ScoringRuleRead:
    rule = await rule_service.create_rule(
        db, organization_id=actor["org_id"],
        name=data.name, field=data.field, operator=data.operator,
        value=data.value, score_delta=data.score_delta, description=data.description,
    )
    return ScoringRuleRead.model_validate(rule, from_attributes=True)


@router.patch("/{rule_id}", response_model=ScoringRuleRead)
async def update_scoring_rule(
    rule_id: int,
    data: ScoringRuleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ScoringRuleRead:
    rule = await rule_service.update_rule(
        db, rule_id=rule_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return ScoringRuleRead.model_validate(rule, from_attributes=True)


@router.delete("/{rule_id}", status_code=204)
async def delete_scoring_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await rule_service.delete_rule(db, rule_id=rule_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")


@router.post("/score/{contact_id}")
async def score_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """Apply all active scoring rules to a contact and persist the new score."""
    result = await rule_service.apply_scoring_to_contact(
        db, contact_id=contact_id, organization_id=actor["org_id"],
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return result
