# Strict Quality Checklist

Use this checklist for every substantial change before merge/release.

## Security
- [ ] No secrets/tokens in code, logs, screenshots, or commits.
- [ ] `SECRET_KEY` and `TOKEN_ENCRYPTION_KEY` are set and different.
- [ ] Owner and break-glass accounts are valid and active as intended.
- [ ] No new auth/session bypass paths.

## Reliability
- [ ] Core logic uses typed exceptions (no broad catch in core paths).
- [ ] Async boundaries preserve cancellation (`CancelledError` re-raised).
- [ ] Retry/backoff behavior is explicit in integration sync paths.
- [ ] Fallback behavior is logged and test-covered.

## Quality Gates
- [ ] `ruff check app tests`
- [ ] `python -m mypy`
- [ ] targeted pytest suite for touched modules
- [ ] release checks when preparing deployment

## Data and Storage
- [ ] No schema-breaking assumptions without migration.
- [ ] Retention/cleanup paths remain safe and tested.
- [ ] Sensitive data redaction still enforced in logs/API responses.

## Product and UX
- [ ] Core user flow works (login -> dashboard -> chat -> key integration action).
- [ ] Error responses are actionable and non-sensitive.
- [ ] No obvious regressions in critical templates/pages.

## Final Merge Safety
- [ ] `git status` reviewed (only intended files staged).
- [ ] Commit message is specific and scoped.
- [ ] Rollback path understood for this change.
