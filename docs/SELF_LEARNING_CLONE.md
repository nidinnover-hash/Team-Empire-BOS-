# Self-Learning Clone (EmpireO First, Multi-Org Ready)

This layer makes the clone improve from operational data, not opinion.

## What is implemented

1. Email Control Loop
- `GET /api/v1/email/control/report-template`
- `POST /api/v1/email/control/process`
- `GET /api/v1/email/control/pending-digest`
- `POST /api/v1/email/control/pending-digest/draft`

Behavior:
- Classifies inbound emails as `fyi|action|approval|escalation`
- Creates tasks for action/escalation emails
- Creates draft + approval for approval-type emails
- Generates owner-wise pending action digest drafts daily

2. Clone Brain Performance Loop
- `POST /api/v1/ops/clones/train?week_start=YYYY-MM-DD`
- `GET /api/v1/ops/clones/scores?week_start=YYYY-MM-DD`
- `GET /api/v1/ops/clones/summary?week_start=YYYY-MM-DD`
- `POST /api/v1/ops/clones/dispatch-plan`

Behavior:
- Trains weekly employee clone readiness from:
  - task metrics
  - code metrics
  - communication metrics
- Produces data-driven readiness tiers:
  - `elite`, `strong`, `developing`, `needs_support`
- Recommends top clones for complex challenges

## Configuration

Set in `.env`:
- `EMAIL_CONTROL_REPORT_SUBJECT_PREFIX=[REPORT]`
- `EMAIL_CONTROL_DIGEST_ENABLED=true`
- `EMAIL_CONTROL_DIGEST_TO=admin@empireoe.com`
- `EMAIL_CONTROL_DIGEST_HOUR_IST=18`
- `EMAIL_CONTROL_DIGEST_MINUTE_IST=0`

## Multi-org strategy

- All tables are `organization_id` scoped.
- EmpireO can run as org 1 now.
- Additional orgs can be added without schema redesign.

## Suggested operational flow

1. Run integration sync hourly (already in scheduler).
2. Trigger `POST /api/v1/email/control/process` after email sync.
3. Run clone training weekly with Monday week_start.
4. Use dispatch plan endpoint for high-complexity assignments.
5. Review digest draft approvals daily before sending.
