# 7-Day Improvement Roadmap

This roadmap is designed to improve reliability, security, and maintainability without destabilizing current behavior.

## Day 1: Error Policy and Baseline
- Adopt [ERROR_HANDLING_POLICY.md](ERROR_HANDLING_POLICY.md).
- Remove unsafe broad catches in core paths.
- Baseline command:
```powershell
python -m mypy app/main.py app/services/memory.py app/services/sync_scheduler.py app/services/github_service.py
python -m pytest -q tests/test_sync_scheduler.py tests/test_memory_crud.py tests/test_memory_layers.py tests/test_github_integration.py tests/test_hardening_round3.py
```
- Done when: checks are green and policy is linked in docs.

## Day 2: Integration Failure Contracts
- Add/extend tests for GitHub/ClickUp/Slack/Stripe:
  - timeout
  - malformed response
  - partial failure
  - retry path
- Done when: failures are isolated and do not stop full sync loop.

## Day 3: Config and Secret Safety
- Enforce startup validation on required security settings.
- Confirm `.env.example` and deploy examples are current.
- Run secret scanning locally and in CI.
- Done when: startup fails fast for unsafe configs.

## Day 4: Scheduler Resilience and Shutdown Safety
- Verify cancellation behavior across background tasks.
- Add tests ensuring `asyncio.CancelledError` is not swallowed.
- Done when: shutdown is clean, no stuck tasks.

## Day 5: Observability Quality
- Standardize error logs with org/integration context.
- Add/verify metrics endpoint usage in runbook.
- Done when: on-call can identify failing integration in <5 minutes.

## Day 6: Storage and Retention Hygiene
- Validate retention cleanup jobs and test coverage.
- Confirm old snapshots/logs/chat cleanup runs safely.
- Done when: retention tests pass and storage growth is bounded.

## Day 7: Release Readiness and Branch Gate
- Run full CI + release-readiness workflow.
- Review high-churn files in GitLens before merge.
- Done when: release checklist is green and risks documented.

## Ongoing Weekly Cadence
- Daily: run targeted checks before merge.
- Weekly: run full test suite and review top-churn files in GitLens.
- Monthly: review integration token scopes, rotation policy, and audit logging.
