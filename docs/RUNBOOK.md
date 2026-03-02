# Runbook

## First 5 Commands (Production Incident Triage)

```bash
cd /opt/nidin-bos
sudo systemctl status nidin-bos --no-pager -l
sudo journalctl -u nidin-bos -n 200 --no-pager
curl -i http://127.0.0.1:8000/health
python scripts/preflight_deploy.py --skip-db
```

## CI Failing on GitHub

1. Open the failed workflow run and copy the first failing step output.
2. Reproduce locally:
   - `python -m mypy`
   - `ruff check app tests`
   - `python3.12 -m pytest -q -p no:cacheprovider`
   - `python3.12 scripts/check_secret_patterns.py`
   - `python3.12 scripts/check_endpoint_complexity.py`
   - `python scripts/check_frontend_guards.py`
3. Fix and push only minimal scoped changes.
4. Re-run workflow.

## Deploy Failure / Rollback

1. Run dry run first:
   - `bash deploy/deploy.sh --dry-run --require-backup /opt/nidin-bos nidin-bos /opt/nidin-bos/.env`
2. Deploy:
   - `bash deploy/deploy.sh --require-backup /opt/nidin-bos nidin-bos /opt/nidin-bos/.env`
3. If health fails, script auto-rolls back to previous commit.
4. Verify rollback:
   - `curl -i http://127.0.0.1:8000/health`
   - `sudo journalctl -u nidin-bos -n 200 --no-pager`

## Webhook Delivery Incidents

1. Check failing deliveries in `/api/v1/webhooks/{id}/deliveries`.
2. Confirm target host is permitted by `WEBHOOK_HOST_ALLOWLIST`.
3. Tune retry knobs if required:
   - `WEBHOOK_DELIVERY_MAX_ATTEMPTS`
   - `WEBHOOK_DELIVERY_BACKOFF_SECONDS`
   - `WEBHOOK_DELIVERY_MAX_BACKOFF_SECONDS`
4. Re-test endpoint with `/api/v1/webhooks/{id}/test`.

## Production Readiness Checklist

- Startup validation enabled (`ENFORCE_STARTUP_VALIDATION=true`)
- `COOKIE_SECURE=true`
- `TOKEN_ENCRYPTION_KEY` set and different from `SECRET_KEY`
- Non-SQLite database in production
- CI checks green before deploy
