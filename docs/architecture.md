# Architecture

## Layers
1. Interface: Web dashboard first.
2. Brain: role-based assistant behavior.
3. Memory: profile/project/daily memory.
4. Tools: external integrations with approval gates.
5. Control: RBAC + audit logging + explicit approvals.

## Current Implementation Baseline
- Existing personal APIs remain available.
- New protected ops API at `/api/v1/ops/*`.
- Every ops write route records an event in `events`.

## Target Modules
- `app/agents`: task planning and execution orchestration.
- `app/memory`: long/short-term memory services.
- `app/tools`: external connectors and action wrappers.
- `app/logs`: audit trail and compliance helpers.

## Next Build Milestones
1. Add `users` table and persistent role model.
2. Introduce approvals workflow table/endpoints.
3. Move from SQLite to Postgres with Alembic migrations.
