# SLO and Error Budget Policy

## Scope
This policy covers API availability and latency for production organizations.

## Service Level Objectives (monthly)
- Availability SLO: `99.9%` successful requests (`2xx/3xx`) for core API traffic.
- Error SLO: `<= 0.1%` server errors (`5xx`) on core API traffic.
- Latency SLO: `p95 <= 800ms` for:
  - `/health`
  - `/api/v1/ops/daily-run`
  - `/api/v1/integrations/*`

## Error budget
- Monthly error budget: `43m 49s` downtime equivalent at `99.9%`.
- If budget burn is above `50%` before day 15:
  - Freeze risky feature launches.
  - Prioritize reliability fixes only.
- If budget burn is above `80%` at any time:
  - Activate change freeze except incident fixes.
  - Require CEO/ADMIN approval for non-critical deploys.

## Alert thresholds
- Page on-call when:
  - 5xx rate > `1.0%` for 10 minutes, or
  - p95 latency > `1200ms` for 10 minutes, or
  - `/health` fails 3 checks in a row.

## Deploy and rollback policy
- If rolling 24h error budget burn is above `30%`, block non-critical deploys.
- If rolling 24h error budget burn is above `50%`, require rollback plan approval before deploy.
- If rolling 24h error budget burn is above `70%`, auto-recommend rollback to last known-good release.

## Weekly review
- Review:
  - 5xx trend
  - Retry rate
  - Idempotency conflicts
  - Rate-limit denies
  - Integration sync failure rates
- Record actions in incident tracker or reliability backlog.
