# Release Safety Playbook

## Purpose
Standardize safe deploys, fast rollback, and post-deploy validation.

## Pre-Deploy
1. Run full gate: `py -3.12 scripts/check_ready.py`
2. Confirm migration chain/head:
   `py -3.12 scripts/check_migration_heads.py`
3. Validate critical indexes:
   `py -3.12 scripts/check_critical_indexes.py`
4. Confirm feature-flag rollout plan for risky changes:
   - target orgs
   - rollout percentages
   - fallback flag state
5. Prepare rollback notes:
   - migration downgrade command
   - feature-flag revert payload
   - expected recovery time objective

## Deploy Strategy
1. Deploy in canary mode:
   - internal orgs first
   - 5%-10% rollout for risky features
2. Monitor first 15 minutes:
   - scheduler SLO breach notifications
   - webhook dead-letter growth
   - 5xx/error spikes
3. Expand rollout gradually:
   - 10% -> 25% -> 50% -> 100%
   - wait for stability at each step

## Rollback Strategy
1. Disable risky feature flags at org level.
2. Revert application release.
3. If required, downgrade latest migration:
   `alembic downgrade -1`
4. Replay dead-letter webhooks after stabilization:
   `POST /api/v1/webhooks/deliveries/{delivery_id}/replay`

## Post-Deploy Smoke
1. Auth:
   - login
   - `/api/v1/mfa/status`
2. Integrations:
   - `/api/v1/integrations/security-center`
   - `/api/v1/integrations/security-center/trend?limit=14`
3. Governance/Ops:
   - `/api/v1/governance/policy-drift`
   - `/api/v1/ops/incident/command-mode`
4. Control:
   - `/api/v1/control/health-summary`
   - `/api/v1/control/trend/metrics`
5. Webhooks:
   - `/api/v1/webhooks/deliveries/all`
   - `/api/v1/webhooks/deliveries/dead-letter`

## Exit Criteria
- No startup validation errors
- No scheduler SLO breach alerts for 24h
- Dead-letter volume stable or decreasing
- No critical security event anomalies
