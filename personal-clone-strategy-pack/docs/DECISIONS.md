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

## ADR-004: Explicit Memory Write Gate in Agent Chat
Date: 2026-02-22
Decision: Agent chat can persist profile memory only when the user message explicitly includes "remember" semantics.
Reason: Prevent accidental long-term memory pollution and keep memory updates intentional and auditable.

## ADR-005: Approval-Linked Email Send Only
Date: 2026-02-22
Decision: Email sending is bound to `emails.approval_id`; send is allowed only when the linked approval is approved, org-scoped, payload email_id-matched, and not yet executed.
Reason: Eliminate approval bypass/replay risk and enforce deterministic approval-to-execution linkage.

## ADR-006: Gmail Draft-First Workflow
Date: 2026-02-22
Decision: Draft flow creates/stores `gmail_draft_id` and creates pending approval before any send path is possible.
Reason: Preserve human review workflow and keep "draft only" behavior as default-safe.

## ADR-007: Org-Scoped Email Uniqueness
Date: 2026-02-22
Decision: Replace global `emails.gmail_id` uniqueness with composite unique `(organization_id, gmail_id)`.
Reason: Maintain tenant isolation and avoid cross-org collisions during sync/import.

## ADR-008: Token Encryption at Rest for Integrations
Date: 2026-02-22
Decision: Store OAuth tokens encrypted in `integrations.config_json` using app-level crypto helpers.
Reason: Reduce secret exposure risk in DB dumps and operational tooling.

## ADR-009: Security-First Dashboard Access
Date: 2026-02-22
Decision: `/` dashboard requires authenticated web session; anonymous requests are redirected to `/web/login`.
Reason: Prevent unauthenticated access to org data and align web surface with API security posture.

## ADR-010: Outcome-Focused Observability Events
Date: 2026-02-22
Decision: Add explicit outcome events for critical control points, including `agent_memory_written`, `agent_memory_write_skipped`, and `email_send_blocked` with reason codes.
Reason: Improve incident debugging, compliance traceability, and operational confidence without changing business logic.
