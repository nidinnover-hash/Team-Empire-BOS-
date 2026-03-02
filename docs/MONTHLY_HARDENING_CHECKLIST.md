# Monthly Hardening Checklist

Run this checklist once per month.

## Security
- [ ] Rotate break-glass credentials and confirm access path.
- [ ] Run `python3.12 scripts/check_secret_patterns.py`.
- [ ] Run `python3.12 scripts/check_env_schema.py`.
- [ ] Review API key scopes and revoke stale/over-broad keys.
- [ ] Run webhook secret rotation drill:
  - `python3.12 scripts/rotation_drill.py`
  - Optional apply: `python3.12 scripts/rotation_drill.py --apply`

## Reliability
- [ ] Verify migration head integrity:
  - `python3.12 scripts/check_migration_heads.py`
- [ ] Verify endpoint growth budgets:
  - `python3.12 scripts/check_endpoint_file_sizes.py`
  - `python3.12 scripts/check_endpoint_complexity.py`
- [ ] Review dead-letter webhook deliveries and retry outcomes.
- [ ] Validate rollback procedure against latest production release.

## Testing and Isolation
- [ ] Run tenancy isolation tests:
  - `python3.12 -m pytest -q tests/test_org_isolation.py tests/test_org_isolation_extended.py -p no:cacheprovider`
- [ ] Run sandbox contracts (if tokens configured):
  - `python3.12 -m pytest -q tests/test_integration_sandbox_contracts.py -p no:cacheprovider`

## Observability and SLO
- [ ] Review 5xx error budget burn and p95 latency trends.
- [ ] Confirm alert thresholds still map to current traffic patterns.
- [ ] Confirm incident playbook owners and escalation contacts are current.
