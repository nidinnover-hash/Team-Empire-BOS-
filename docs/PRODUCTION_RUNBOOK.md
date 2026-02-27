# Production Runbook

Related controls:
- `docs/SLO_ERROR_BUDGET.md`
- `docs/INCIDENT_RESPONSE_PLAYBOOK.md`
- `docs/BACKUP_RESTORE_DRILL.md`

## Deploy
1. Confirm release gate: `python scripts/check_ready.py`
2. Run deploy:
   - `bash deploy/deploy.sh /opt/personal-clone personal-clone /opt/personal-clone/.env`
3. Verify:
   - `curl -fsS http://127.0.0.1:8000/health`
   - `journalctl -u personal-clone --since "10 minutes ago"`
   - `journalctl -u personal-clone-scheduler --since "10 minutes ago"`

## Security-critical env defaults
Set these explicitly in production:
- `COOKIE_SECURE=true`
- `TOKEN_ENCRYPTION_KEY` set, 32+ chars, and different from `SECRET_KEY`
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
4. Restart services:
   - `systemctl restart personal-clone`
   - `systemctl restart personal-clone-scheduler`
5. Re-check health and logs.

## Incident response priorities
1. Authentication outage: verify env keys, token signing keys, cookie settings.
2. Integration outage: inspect provider token validity and API rate limits.
3. Database errors: verify connectivity, migrations, pool settings.
4. High error rate: check recent deploy diff and roll back if needed.

## Credential rotation
1. Rotate one provider token/key at a time.
2. Update `.env`, restart services, verify provider health endpoint.
3. Revoke old credentials after validation.

## Forensics and audit
1. Capture request IDs and timestamps from logs.
2. Export relevant audit/decision rows by `organization_id`.
3. Preserve the exact app commit hash and env version used during incident window.
