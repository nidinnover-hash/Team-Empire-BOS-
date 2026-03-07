# Current Task Template

Use this file to document the current feature being developed. Update it before starting work so all AI assistants have shared context.

---

## Feature Name

_[Name of the feature or module being built]_

## Goal

_[One-sentence description of what this feature achieves]_

## Requirements

- [ ] _[Requirement 1]_
- [ ] _[Requirement 2]_
- [ ] _[Requirement 3]_

## Files to Create

| File | Purpose |
|------|---------|
| `app/services/xxx.py` | _Service logic_ |
| `app/api/v1/endpoints/xxx.py` | _API endpoint_ |
| `tests/test_xxx.py` | _Test coverage_ |

## Files to Modify

| File | Change |
|------|--------|
| `app/core/config.py` | _Add feature flag_ |

## Constraints

- Must follow existing service layer pattern (thin routes, logic in services)
- Must respect RBAC — use `require_roles()` on all endpoints
- Must generate audit events for write operations
- Must not break existing tests
- Feature-flagged behind `FEATURE_XXX` setting

## Validation

- [ ] All new tests pass
- [ ] Full test suite green (1986+ tests)
- [ ] No security vulnerabilities introduced
- [ ] Audit events recorded for mutations
- [ ] Feature flag correctly gates the functionality

## Risks

| Risk | Mitigation |
|------|------------|
| _[Risk description]_ | _[How to mitigate]_ |

## Status

- [ ] Planning
- [ ] Implementation
- [ ] Tests written
- [ ] Full suite passing
- [ ] Deployed to production
