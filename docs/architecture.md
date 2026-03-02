# Architecture

## Layers
1. Interface: Web dashboard first.
2. Brain: role-based assistant behavior.
3. Memory: profile/project/daily memory.
4. Tools: external integrations with approval gates.
5. Control: RBAC + audit logging + explicit approvals.

## Current Implementation Baseline
- Existing personal APIs remain available.
- Protected ops APIs are active at `/api/v1/ops/*`.
- Ops writes are audited in `events`.
- Multi-org RBAC, approvals, webhook delivery logs, and API key management are live.
- Integration tokens are encrypted at rest.

## Target Modules
- `app/agents`: task planning and execution orchestration.
- `app/memory`: long/short-term memory services.
- `app/tools`: external connectors and action wrappers.
- `app/logs`: audit trail and compliance helpers.

## Next Build Milestones
1. Complete API-key scope matrix across all endpoints (beyond read/write baseline).
2. Move webhook delivery into a durable worker queue for higher throughput.
3. Add end-to-end integration contract tests against provider sandboxes.
