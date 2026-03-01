# Engineering Operations Guide

## Branch Protection
- Protect `main`.
- Require pull request before merge.
- Require status checks: `fast-checks`, `full-checks`, `secret-scan`.
- Require branch to be up to date before merge.
- Restrict force-push and direct pushes to `main`.

## Required Pre-Merge Checks
- `python3.12 scripts/preflight_python.py`
- `python3.12 scripts/check_ops_readiness.py`
- `python3.12 scripts/check_ready.py`
- `ruff check app tests`
- `python3.12 -m mypy`
- `python3.12 -m pytest -q -p no:cacheprovider`
- `python3.12 scripts/check_migration_heads.py`
- `pip-audit -r requirements.txt --progress-spinner off`
- `bandit -r app -ll -q`

## Error Budget Dashboard (Weekly)
- API 5xx rate
- Retry rate
- Idempotency conflicts
- Rate-limit blocked requests
- P95 latency for `/api/v1/health`, `/api/v1/ops/daily-run`, `/api/v1/integrations`

## Nightly Sandboxes
- Run `.github/workflows/integration-sandbox-nightly.yml` with sandbox provider tokens.
- Required secrets:
  - `SANDBOX_GITHUB_TOKEN`
  - `SANDBOX_SLACK_BOT_TOKEN`
  - `SANDBOX_NOTION_TOKEN`
- Contract suite:
  - `tests/test_integration_sandbox_contracts.py`

## Release Checklist
- Ensure single Alembic head.
- Run `python3.12 scripts/preflight_python.py`.
- Run `python3.12 scripts/check_ops_readiness.py`.
- Run `python3.12 scripts/check_ready.py`.
- Validate startup with production-like env values.
- Confirm rollback command and previous image tag.
- Review privacy profile and redaction tests.
- Review `docs/MONTHLY_HARDENING_CHECKLIST.md` and close open items.
