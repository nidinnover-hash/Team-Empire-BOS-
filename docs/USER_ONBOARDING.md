# User Onboarding Guide

This guide is for first-time users of the Nidin BOS command center.

## 1) First-Run Setup (10-15 minutes)

1. Start the app:
   - PowerShell: `./start-local.ps1`
2. Open the UI:
   - `http://127.0.0.1:8000/web/login`
3. Sign in with your account.
4. Confirm core pages load:
   - `/`
   - `/web/talk`
   - `/web/integrations`
   - `/web/tasks`

## 2) First Session Workflow (Day 1)

1. Open Dashboard and review:
   - Open tasks
   - Pending approvals
   - Unread inbox
2. Open Integrations:
   - Connect only what you actively use.
3. Open Talk mode and run 3 prompts:
   - `Prioritize my top 3 tasks for today.`
   - `What approvals need my decision first?`
   - `Build a 2-hour execution plan for my priorities.`
4. Open Tasks:
   - Close stale tasks.
   - Add 3 high-impact tasks.
5. Open Memory Editor:
   - Add preferences in clear language (tone, constraints, priorities).

## 3) Operating Rules (Use Efficiently)

- Use clone output as draft decisions, not blind execution.
- Clear approvals queue daily.
- Keep memory factual and short.
- Ask for ranked output (`top 3`, `by impact`, `next 2 hours`).
- Prefer one intent per prompt for better action quality.

## 4) Prompt Patterns That Work

- Prioritization:
  - `Rank today's tasks by business impact and urgency. Give top 3 with rationale.`
- Execution planning:
  - `Create a 120-minute plan with 30-minute blocks.`
- Decision support:
  - `Give options A/B/C, risks, and your recommended option.`
- Inbox control:
  - `Draft concise replies for urgent threads, approval-safe.`
- Delegation:
  - `Convert this goal into 5 executable tasks with owners and due dates.`

## 5) Daily Cadence (15 minutes + execution)

1. Morning (5 min): dashboard scan + priorities.
2. Midday (5 min): approvals + inbox triage.
3. End of day (5 min): update tasks, add learned memory, queue tomorrow.

## 6) Weekly Cadence

- Run clone training weekly (Monday recommended):
  - `POST /api/v1/ops/clones/train?week_start=YYYY-MM-DD`
- Review score and summary:
  - `GET /api/v1/ops/clones/scores?week_start=YYYY-MM-DD`
  - `GET /api/v1/ops/clones/summary?week_start=YYYY-MM-DD`
- Use dispatch plan for complex work:
  - `POST /api/v1/ops/clones/dispatch-plan`

## 7) Common Mistakes to Avoid

- Overloading one prompt with many objectives.
- Keeping outdated memory entries.
- Delaying approvals until backlog forms.
- Connecting integrations you do not monitor.

## 8) Success Metrics (First 2 weeks)

- Approval turnaround time decreases.
- Open-task backlog stays stable or shrinks.
- Daily priorities are completed more consistently.
- Fewer context-switches due to clearer execution plans.
