# Engineering Operations Guide

## Branch Protection
- Protect `main`.
- Require pull request before merge.
- Require status checks: `fast-checks`, `full-checks`, `secret-scan`.
- Require branch to be up to date before merge.
- Restrict force-push and direct pushes to `main`.

## Required Pre-Merge Checks
- `python scripts/check_ops_readiness.py`
- `python scripts/check_ready.py`
- `ruff check app tests`
- `python -m mypy`
- `python -m pytest -q -p no:cacheprovider`
- `python scripts/check_migration_heads.py`
- `pip-audit -r requirements.txt --progress-spinner off`
- `bandit -r app -ll -q`

## Error Budget Dashboard (Weekly)
- API 5xx rate
- Retry rate
- Idempotency conflicts
- Rate-limit blocked requests
- P95 latency for `/api/v1/health`, `/api/v1/ops/daily-run`, `/api/v1/integrations`

## Release Checklist
- Ensure single Alembic head.
- Run `python scripts/check_ops_readiness.py`.
- Run `python scripts/check_ready.py`.
- Validate startup with production-like env values.
- Confirm rollback command and previous image tag.
- Review privacy profile and redaction tests.
