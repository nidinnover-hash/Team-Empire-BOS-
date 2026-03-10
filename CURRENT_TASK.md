# Current Task

## Feature Name

CRM Expansion: Quotes, Sales Playbooks, and CSAT Surveys

## Goal

Add database-backed CRM modules for quote/proposal management, sales playbooks, and customer surveys that can be consumed by existing services and upcoming API endpoints.

## Requirements

- [x] Define SQLAlchemy models for quotes and quote line items
- [x] Define SQLAlchemy models for sales playbooks and playbook steps
- [x] Define SQLAlchemy models for survey definitions and responses
- [ ] Wire endpoints with RBAC and audit logging
- [ ] Add feature flags for endpoint exposure
- [ ] Add API + service tests for happy path and permission checks

## Files Created

| File | Purpose |
|------|---------|
| `app/models/quote.py` | Quote and quote line item models |
| `app/models/sales_playbook.py` | Playbook and playbook step models |
| `app/models/survey.py` | Survey definition and response models |
| `alembic/versions/20260310_0086_add_crm_quote_playbook_survey_tables.py` | Migration for new CRM tables |

## Files Modified

| File | Change |
|------|--------|
| `alembic/env.py` | Register new model modules for Alembic metadata discovery |
| `CURRENT_TASK.md` | Replace template with active task context |

## Constraints

- Keep routes thin and place business logic in services
- Enforce RBAC with `require_roles()` on mutating endpoints
- Record audit events for all write actions
- Keep changes migration-driven (no manual DB edits)
- Avoid broad refactors unrelated to CRM module rollout

## Validation

- [ ] Migration applies and downgrades cleanly
- [ ] New endpoint/service tests pass
- [ ] Full suite green
- [ ] Audit events present on writes
- [ ] Feature flags gate new endpoints

## Risks

| Risk | Mitigation |
|------|------------|
| Existing local DB drift causes migration mismatch | Keep migration explicit/manual and validate upgrade + downgrade |
| Endpoint rollout without RBAC/audit enforcement | Implement and test endpoints only after service/model layer is stable |

## Status

- [x] Planning
- [x] Model implementation
- [x] Migration scaffolding
- [ ] API layer implementation
- [ ] Tests written
- [ ] Full suite passing
