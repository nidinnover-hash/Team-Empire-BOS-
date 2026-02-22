# Decisions (ADRs)

## ADR-001: Keep Existing Personal APIs Intact
Date: 2026-02-21
Decision: Add new protected ops routes instead of breaking existing personal routes.
Reason: Preserve current functionality/tests while introducing architecture controls.

## ADR-002: Add Event-Driven Audit Baseline
Date: 2026-02-21
Decision: Introduce `events` table and service now.
Reason: Every future automation depends on traceability.

## ADR-003: RBAC via dependency layer
Date: 2026-02-21
Decision: Add `require_roles(...)` dependency in API endpoints.
Reason: Enforce server-side role checks with minimal code overhead.
