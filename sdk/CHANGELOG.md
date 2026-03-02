# SDK Changelog

## 0.7.0 - 2026-03-02

- Added tested PR checklist rule engine (`scripts/pr_checklist_guard.py`) and wired PR workflow to use it.
- Added SDK release notes validation (`scripts/check_sdk_release_notes.py`) to fail release on empty/placeholder notes.
- Added mutating-operation allowlist in SDK client generator to reduce accidental surface expansion risk.
- Expanded SDK generation coverage tests to include mutating operations.
- Extended `dev_gate` with PR checklist guard tests.

## 0.6.0 - 2026-03-02

- Added PR checklist guard workflow with conditional migration/SDK checklist enforcement.
- Added `dev-gate` CI lane and made full CI depend on it.
- Added deterministic SDK generation test coverage.
- Added GET-operation generation coverage tests for Python/TypeScript SDK clients.
- Added explicit SDK client generation parity check script and CI wiring.
- Added automated SDK release notes generation (`sdk/release-notes.md`) in release workflow.
- Added branch protection audit workflow and updated required-check documentation.

## 0.5.0 - 2026-03-02

- Added OpenAPI operationId-driven SDK client method generation via `scripts/generate_sdk_clients.py`.
- Integrated generated client drift checks into SDK CI and SDK release workflows.
- Added fast local developer gate command `scripts/dev_gate.py`.

## 0.4.0 - 2026-03-02

- Added migration revision guardrails (`check_migration_revisions.py`) and integrated them into readiness/CI.
- Added OpenAPI change-tier classification (`patch`/`minor`/`major`) and semver-aware SDK version bump enforcement.
- Expanded SDK live contract smoke coverage to organizations and automation endpoints.
- Upgraded SDK type generation to operation-driven path-prefix selection for broader schema coverage.
- Added developer health preflight (`scripts/dev_health.py`) and CI risk report artifacts.
- Added release provenance metadata (`sdk/release-provenance.json`) in release workflow artifacts.

## 0.3.0 - 2026-03-02

- Added stable OpenAPI `operationId` generation based on HTTP method + normalized path.
- Added PR-time OpenAPI breaking-change detection against the base branch schema.
- Added request observability hooks to Python (`on_request_event`) and TypeScript (`onRequestEvent`) SDK clients.
- Added Python SDK tests for quota/rate-limit error semantics and request event emission.
- Added SDK usage examples for Python and TypeScript.
- Hardened release workflow with npm package dry-run, artifact checksums, and artifact upload.

## 0.2.0 - 2026-03-02

- Expanded generated SDK coverage to tasks, approvals, and webhook deliveries.
- Added live contract smoke tests (Python + TypeScript) against a running app in CI.
- Added PR guard to enforce SDK version bump + changelog updates for SDK surface changes.
- Added tag-gated release automation workflow for PyPI/npm publishing.

## 0.1.0 - 2026-03-02

- Added OpenAPI export + SDK type generation for Python and TypeScript.
- Added Python and TypeScript SDK clients with retry/backoff and quota-aware 429 handling.
- Added CI SDK drift + packaging/build smoke checks.
