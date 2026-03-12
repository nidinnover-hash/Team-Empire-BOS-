# Control layer — structured logging

For observability, every control endpoint should be traceable with:

- **organization_id** — tenant
- **actor_user_id** — who performed the action
- **entity_type** / **entity_id** — what was affected
- **request_id** — from `get_current_request_id()` for correlation

Control mutations already call `record_critical_mutation()` (and thus `record_action()`), which stores these in the `events` table. For ad-hoc logging in control code, use the same fields so logs and events can be correlated.

**Report:** `GET /api/v1/control/observability/control-report` returns counts of control events (e.g. placement_confirmed, money_approval_requested) by type and by organization over the last 7 days.
