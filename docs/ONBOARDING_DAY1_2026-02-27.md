# Day 1 Onboarding Run - Friday, February 27, 2026

Use this exact runbook for your first operator session.

## Session Window (45 minutes)

- 09:00-09:05: Sign in + page health
- 09:05-09:15: Integrations and baseline snapshot
- 09:15-09:30: Talk mode prompt drill
- 09:30-09:40: Task and approvals discipline
- 09:40-09:45: Memory seeding and wrap-up

## Step-by-Step

1. Start local app:
- `./start-local.ps1`

2. Login and verify pages:
- `/`
- `/web/talk`
- `/web/integrations`
- `/web/tasks`

3. Capture baseline metrics from dashboard:
- Open tasks
- Pending approvals
- Unread inbox

4. Connect at least one active integration:
- Prefer the integration you use daily.

5. In Talk mode, run exactly these prompts:
- `Prioritize my top 3 tasks for today.`
- `What approvals need my decision first?`
- `Build a 2-hour execution plan for my priorities.`

6. In Tasks view:
- Add 3 high-impact tasks.
- Close stale/obsolete tasks.

7. In Memory editor:
- Add 3 profile memory items (tone, constraints, priorities).

8. End-of-session check:
- Approval queue is current.
- Top 3 priorities are clear.
- One 2-hour plan is ready to execute.

## Pass Criteria

- User navigates core pages without assistance.
- User gets a usable daily plan from Talk mode.
- User maintains a clean approvals queue.
- User seeds memory with at least 3 quality entries.

## References

- `docs/USER_ONBOARDING.md`
- `docs/TRAINING_CURRICULUM_7_DAYS.md`
