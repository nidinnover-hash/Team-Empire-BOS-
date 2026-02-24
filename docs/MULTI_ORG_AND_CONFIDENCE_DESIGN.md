# Multi-Org Schema + Agent Confidence Design

## Multi-Org Schema

New tables:
- `organization_memberships`
  - `(organization_id, user_id)` unique
  - `role` per org
  - `is_active`, `created_at`, `updated_at`
- `organization_role_permissions`
  - org-scoped role -> permission mapping
  - unique `(organization_id, role, permission)`

Why:
- Supports users belonging to multiple organizations
- Decouples per-org role from legacy single `users.role`
- Enables custom authorization profiles per organization

## Agent Confidence Scoring

`app/services/confidence.py` adds deterministic confidence assessment for
agent responses:
- score: `0-100`
- level: `low|medium|high`
- reasons: top scoring factors
- needs_human_review: final safety flag

Current signals:
- memory context presence
- response quality/length
- provider error detection
- risky user intent keywords
- manual approval requirement

The `/api/v1/agents/chat` response now includes:
- `confidence_score`
- `confidence_level`
- `confidence_reasons`
- `needs_human_review`

This keeps the system explainable and aligned to suggest-only operations.
