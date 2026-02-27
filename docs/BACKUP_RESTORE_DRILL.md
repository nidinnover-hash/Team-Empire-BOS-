# Backup and Restore Drill

## Frequency
- Run monthly in staging.
- Run quarterly in production maintenance window.

## Preconditions
- Confirm latest backup exists:
  - `POST /api/v1/control/backup`
  - `GET /api/v1/control/backup/list`
- Record backup file name, size, and timestamp.

## Drill steps
1. Create a fresh backup.
2. Restore into an isolated test database.
3. Boot app against restored DB.
4. Run smoke checks:
   - `/health`
   - approval request + approve flow
   - integration status endpoint
5. Validate tenant boundaries:
   - org A token cannot access org B data.

## Success criteria
- Restore completes without manual data edits.
- Core endpoints pass smoke checks.
- No cross-tenant access appears in validation checks.
- RTO <= 30 minutes and RPO <= 24 hours.

## Failure handling
1. Mark drill as failed and open reliability incident.
2. Keep failing backup artifact for analysis.
3. Add corrective action and retest within 7 days.
