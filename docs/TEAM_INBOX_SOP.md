# Team Inbox SOP

Standard operating procedure for daily conversation handling across email and WhatsApp.

## Morning Run (15 minutes)

1. Open active queue:
- `GET /api/v1/inbox/conversations?limit=100`

2. Prioritize:
- Handle `priority=urgent/high` first.
- Then handle earliest `sla_due_at`.

3. Assign ownership:
- For unowned conversations, assign an owner:
- `PATCH /api/v1/inbox/conversations/{conversation_id}/assign`
```json
{"owner_user_id": 2}
```

4. Set workflow state:
- Move active items to review/work:
- `PATCH /api/v1/inbox/conversations/{conversation_id}/state`
```json
{"status":"in_review","priority":"high","sla_due_at":"2026-02-23T18:00:00Z"}
```

5. Pull latest channel content:
- Sync Gmail from dashboard or call `POST /api/v1/email/sync`.
- For key emails:
- `POST /api/v1/email/{email_id}/summarize`
- `POST /api/v1/email/{email_id}/draft-reply`

6. Execute pending approvals:
- List pending approvals:
- `GET /api/v1/approvals?status=pending`
- Approve actionable sends:
- `POST /api/v1/approvals/{approval_id}/approve`
```json
{"note":"YES EXECUTE"}
```

## Midday Check (10 minutes)

1. Re-open queue:
- `GET /api/v1/inbox/conversations?limit=100`

2. Check SLA risk:
- Find overdue or near-due items.

3. Rebalance ownership:
- Reassign overloaded owners:
- `PATCH /api/v1/inbox/conversations/{conversation_id}/assign`

4. Mark blockers:
- Set blocked/external dependency items:
- `PATCH /api/v1/inbox/conversations/{conversation_id}/state`
```json
{"status":"waiting","priority":"high"}
```

## Evening Close (10 minutes)

1. Close completed threads:
- `PATCH /api/v1/inbox/conversations/{conversation_id}/state`
```json
{"status":"done","priority":"medium","sla_due_at":null}
```

2. Carry forward unresolved items:
- Keep as `in_review` with refreshed SLA for next day.

3. Final approval sweep:
- `GET /api/v1/approvals?status=pending`
- Approve/reject before day-end.

## Team Rules

1. Every active conversation must have an owner.
2. No `urgent/high` conversation without an SLA.
3. No outbound send without explicit approval (`YES EXECUTE`).
4. End of day should have no stale `new` conversations.

## Conversation Status Definition

- `new`: Not triaged yet.
- `in_review`: Assigned and actively worked.
- `waiting`: Waiting on external dependency/user response.
- `done`: Completed and closed.

## Priority Definition

- `low`: Can wait.
- `medium`: Normal queue.
- `high`: Needs same-day action.
- `urgent`: Immediate action required.
