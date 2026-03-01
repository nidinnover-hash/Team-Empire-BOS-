# Production Runbook

Related controls:
- `docs/SLO_ERROR_BUDGET.md`
- `docs/INCIDENT_RESPONSE_PLAYBOOK.md`
- `docs/BACKUP_RESTORE_DRILL.md`

## Deploy
1. Confirm release gate: `python3.12 scripts/check_ready.py`
2. Confirm production config smoke check:
   - `python3.12 scripts/smoke_prod_config.py --import-app`
   - Must pass with production-like env (`DEBUG=false`, `COOKIE_SECURE=true`, `AUTO_CREATE_SCHEMA=false`, `AUTO_SEED_DEFAULTS=false`).
3. Confirm critical regression suite is green in CI fast-checks:
   - `tests/test_api_smoke_fast.py`
   - `tests/test_super_admin.py`
   - `tests/test_integrations.py`
   - `tests/test_talk_mode.py`
   - `tests/test_config_validation.py`
4. Run deploy:
   - `bash deploy/deploy.sh /opt/nidin-bos nidin-bos /opt/nidin-bos/.env`
   - Optional preflight only (no changes): `bash deploy/deploy.sh --dry-run /opt/nidin-bos nidin-bos /opt/nidin-bos/.env`
   - Require backup tooling before deploy: `bash deploy/deploy.sh --require-backup /opt/nidin-bos nidin-bos /opt/nidin-bos/.env`
5. Verify:
   - `curl -fsS http://127.0.0.1:8000/health`
   - `journalctl -u nidin-bos --since "10 minutes ago"`
   - `journalctl -u nidin-bos-scheduler --since "10 minutes ago"`

## Webhook queue mode
To use DB-backed async webhook dispatch:
- Set `WEBHOOK_ASYNC_DISPATCH_ONLY=true`
- Run webhook worker process:
  - `python3.12 run_webhook_worker.py`
This mode queues deliveries in DB and lets worker retries handle dispatch.

## Security-critical env defaults
Set these explicitly in production:
- `COOKIE_SECURE=true`
- `TOKEN_ENCRYPTION_KEY` set, 32+ chars, and different from `SECRET_KEY`
- `OAUTH_STATE_KEY` set, 32+ chars, and different from both `SECRET_KEY` and `TOKEN_ENCRYPTION_KEY`
- `WEB_API_TOKEN_EXPIRE_MINUTES=10` (short browser API token TTL; keep `<=15`)
- `CORS_ALLOWED_ORIGINS` only trusted HTTPS origins (no `*`, no paths)

## Reverse proxy and client IP trust
Use forwarded headers only behind a trusted proxy.
Recommended values:
- `USE_FORWARDED_HEADERS=true`
- `TRUSTED_PROXY_CIDRS=127.0.0.1/32` when Nginx is local on the app host
- `TRUSTED_PROXY_CIDRS=<private-cidr>` when app is behind internal LB/VPC

Do not enable `USE_FORWARDED_HEADERS` without `TRUSTED_PROXY_CIDRS`.
Otherwise `X-Forwarded-For` can be spoofed and weaken rate-limits/login lockout.

## Rollback
1. Checkout previous release tag/commit in app directory.
2. Reinstall dependencies if needed.
3. Run backward-compatible migration or restore DB backup.
   - Restore DB backup: `bash deploy/restore-db.sh --yes /opt/nidin-bos/Data/backups/<backup-file> /opt/nidin-bos/.env`
4. Restart services:
   - `systemctl restart nidin-bos`
   - `systemctl restart nidin-bos-scheduler`
5. Re-check health and logs.

## Incident response priorities
1. Authentication outage: verify env keys, token signing keys, cookie settings.
2. Integration outage: inspect provider token validity and API rate limits.
3. Database errors: verify connectivity, migrations, pool settings.
4. High error rate: check recent deploy diff and roll back if needed.

## CI failure triage
1. `Critical regression suite` fails:
   - Treat as product-path regression.
   - Reproduce locally with the same subset and fix before merge.
2. `Production config smoke` fails:
   - Run `python3.12 scripts/smoke_prod_config.py --import-app` locally with production-like env.
   - Fix invalid env values first (startup validation), then import/runtime issues.
3. `check_ready.py` fails:
   - Follow failing stage order (`ruff`, `mypy`, migrations, tests, security tools).
   - Do not deploy with a red readiness gate.

## Credential rotation
1. Rotate one provider token/key at a time.
2. Update `.env`, restart services, verify provider health endpoint.
3. Revoke old credentials after validation.
4. Run rotation drill monthly:
   - `python3.12 scripts/rotation_drill.py`
   - Optional apply mode for webhook secrets: `python3.12 scripts/rotation_drill.py --apply`

## Forensics and audit
1. Capture request IDs and timestamps from logs.
2. Export relevant audit/decision rows by `organization_id`.
3. Preserve the exact app commit hash and env version used during incident window.
