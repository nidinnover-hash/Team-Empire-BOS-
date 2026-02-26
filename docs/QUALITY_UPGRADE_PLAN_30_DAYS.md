# 30-Day Quality Upgrade Plan

This plan is optimized for a solo builder shipping fast without losing safety.

## Target Outcome
- Reach production-grade reliability and security discipline.
- Keep velocity high through repeatable checklists and automation.

## Week 1: Security and Ownership Hardening
- Rotate exposed/old API keys.
- Enforce secure ownership model (owner + break-glass account).
- Confirm startup validation catches unsafe production config.
- Run:
```powershell
.\.venv\Scripts\python.exe scripts/harden_owner_account.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_config_validation.py tests/test_auth_policy_enforcement.py
```

Definition of done:
- No demo owner accounts active.
- Key separation and secret checks passing.
- Auth policy tests green.

## Week 2: Reliability and Error Boundaries
- Remove broad catches in non-boundary logic.
- Keep boundary catches with explicit cancellation handling.
- Add failure-contract tests for integration sync paths.

Definition of done:
- New/edited core paths use typed exceptions.
- Scheduler/integration failure paths remain resilient and tested.

## Week 3: Observability and Ops Readiness
- Standardize error logs with org/integration context.
- Verify health/sync metrics endpoints and dashboard usage.
- Add incident playbook snippets to runbook.

Definition of done:
- Failing integration can be identified in <5 minutes from logs/metrics.
- Health and sync freshness checks documented.

## Week 4: Release Discipline and Performance
- Enforce strict PR checklist.
- Run release-readiness workflow and rollback drill.
- Track performance budget and fail on regressions.

Definition of done:
- Full quality gate green before merge.
- Rollback path tested and documented.
- No unresolved critical issues in release checklist.

## Daily Routine (10-15 min)
1. Pull latest and review changed critical files.
2. Run targeted quality checks before edits.
3. Run targeted tests after edits.
4. Stage only intended files.
5. Confirm no secrets or debug artifacts.

## Weekly Routine (30-60 min)
1. Run full quality gate.
2. Review high-churn files in GitLens.
3. Rotate/revalidate integration token scopes.
4. Update risk register with top 3 risks.

