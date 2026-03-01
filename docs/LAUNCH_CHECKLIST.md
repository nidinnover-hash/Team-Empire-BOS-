# Launch Checklist

Use this checklist before each production release.

## 1) Config and secrets
- [ ] `DEBUG=false`
- [ ] `ENFORCE_STARTUP_VALIDATION=true`
- [ ] `DB_SCHEMA_ENFORCE_HEAD=true`
- [ ] `COOKIE_SECURE=true`
- [ ] `DATABASE_URL` points to PostgreSQL (not SQLite)
- [ ] `SECRET_KEY` is 32+ chars random
- [ ] `TOKEN_ENCRYPTION_KEY` is set, 32+ chars, and different from `SECRET_KEY`
- [ ] `WEB_API_TOKEN_EXPIRE_MINUTES` is set to short TTL (`10` recommended, max `15`)
- [ ] `CORS_ALLOWED_ORIGINS` contains only trusted HTTPS origins (no wildcard, no path)
- [ ] If behind reverse proxy: `USE_FORWARDED_HEADERS=true` and `TRUSTED_PROXY_CIDRS` is set correctly
- [ ] Provider tokens/secrets are populated only for integrations in use

## 2) Quality gate
- [ ] Run `python3.12 scripts/check_ready.py`
- [ ] Run `python3.12 scripts/preflight_python.py`
- [ ] Confirm zero startup validation issues
- [ ] Confirm migration head check is clean
- [ ] Confirm security scans pass (`pip-audit`, `bandit`)

## 3) Data and migration safety
- [ ] Backup database before deploy
- [ ] Run `alembic upgrade head` in staging and production
- [ ] Verify rollback command and previous image/tag are documented

## 4) Deployment checks
- [ ] Deploy with `deploy/deploy.sh` using the correct `.env` file
- [ ] Health endpoint returns `200` after restart
- [ ] Scheduler service is healthy (`<service>-scheduler`)

## 5) Post-deploy verification
- [ ] Login and critical page load checks (`/web/dashboard`, `/web/integrations`, `/web/talk`)
- [ ] One smoke call for key APIs (`/api/v1/health`, `/api/v1/ops/*`, `/api/v1/email/health`)
- [ ] Validate at least one critical integration sync path

## 6) Monitoring and alerts
- [ ] Track 5xx errors, sync failures, idempotency conflicts, rate-limit blocks
- [ ] Alert on repeated provider failures (GitHub/Gmail/ClickUp)
- [ ] Review logs for fallback warnings (Redis/API parsing)
