# Quality Checklist

Use this before every commit/merge.

## 1) Security
- [ ] No secrets/tokens/passwords in code, logs, or tests.
- [ ] Auth-protected endpoints use DB-backed user validation.
- [ ] `token_version` is included in issued tokens and validated on read.
- [ ] Purpose/data-lane barriers are enforced (professional/personal/entertainment).

## 2) Reliability
- [ ] No silent `pass` in production code paths.
- [ ] Exception handlers include actionable context (`org_id`, operation, provider).
- [ ] Background jobs log failures and include thresholds/alerts.
- [ ] Health checks degrade gracefully and emit clear diagnostics.

## 3) API correctness
- [ ] Status/state transitions are explicitly validated.
- [ ] Endpoint responses use schemas with consistent error envelopes.
- [ ] Idempotency/conflict paths return correct HTTP status codes.

## 4) Data integrity
- [ ] Migrations are linear and head-consistent.
- [ ] New schema changes include migration + rollback.
- [ ] Unique constraints/indexes match intended query patterns.

## 5) Test gates
- [ ] Fast smoke tests pass.
- [ ] Regression tests added for each bug fixed.
- [ ] `ruff`, `mypy`, and targeted pytest pass locally.
- [ ] CI workflow includes lint/type/security/migration checks.

## 6) Release readiness
- [ ] Startup validation passes in production mode.
- [ ] Observability/logging includes request/job context.
- [ ] Risky behavior is `suggest_only` unless explicitly approved.
