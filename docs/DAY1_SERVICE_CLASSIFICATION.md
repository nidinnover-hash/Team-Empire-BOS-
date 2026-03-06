# Day 1 Service Classification

Date: 2026-03-06

This is the first-pass classification of the highest-impact existing modules into the target architecture.

The purpose is to stop further drift and provide a stable migration target.

## Brain Engine Targets

- `app/services/ai_router.py` -> `app/engines/brain/router.py`
- `app/services/context_builder.py` -> `app/engines/brain/context.py`
- `app/services/confidence.py` -> `app/engines/brain/confidence.py`
- `app/services/agent_policy.py` -> `app/engines/brain/policy.py`
- `app/agents/orchestrator.py` -> `app/engines/brain/drafting.py`

## Decision Engine Targets

- `app/services/approval.py` -> `app/engines/decision/approvals.py`
- `app/services/approval_pattern.py` -> `app/engines/decision/policy.py`
- `app/services/autonomy_policy.py` -> `app/engines/decision/policy.py`
- `app/services/decision_card.py` -> `app/engines/decision/planner.py`
- `app/services/compliance_engine.py` -> `app/engines/decision/evaluator.py`

## Execution Engine Targets

- `app/services/execution_engine.py` -> `app/engines/execution/executor.py`
- `app/services/execution.py` -> `app/engines/execution/journal.py`
- `app/services/webhook.py` -> `app/engines/execution/handlers/webhook.py`

## Intelligence Engine Targets

- `app/services/intelligence.py` -> `app/engines/intelligence/aggregation.py`
- `app/services/cross_layer_intelligence.py` -> `app/engines/intelligence/patterns.py`
- `app/services/briefing.py` -> `app/engines/intelligence/briefings.py`
- `app/services/report_service.py` -> `app/engines/intelligence/projections.py`
- `app/services/metrics_service.py` -> `app/engines/intelligence/metrics.py`

## Application Layer Targets

- `app/web/chat.py` -> call `app/application/chat/service.py`
- `app/web/pages.py` -> call `app/application/dashboard/service.py`
- `app/services/chat_history.py` -> `app/application/chat/service.py`
- `app/services/conversation.py` -> `app/application/chat/service.py`
- `app/services/daily_run.py` -> `app/application/orchestration/daily_run.py`
- `app/services/sync_scheduler.py` -> `app/application/integrations/scheduler.py`

## Domain Targets

- `app/services/organization.py` -> `app/domains/organizations/service.py`
- `app/services/workspace.py` -> `app/domains/workspaces/service.py`
- `app/services/user.py` -> `app/domains/users/service.py`
- `app/services/task.py` -> `app/domains/tasks/service.py`
- `app/services/project.py` -> `app/domains/projects/service.py`
- `app/services/goal.py` -> `app/domains/goals/service.py`
- `app/services/note.py` -> `app/domains/notes/service.py`
- `app/services/contact.py` -> `app/domains/contacts/service.py`
- `app/services/finance.py` -> `app/domains/finance/service.py`
- `app/services/memory.py` -> `app/domains/memory/service.py`

## Adapter Targets

- `app/services/gmail_service.py` -> `app/adapters/integrations/gmail/service.py`
- `app/services/slack_service.py` -> `app/adapters/integrations/slack/service.py`
- `app/services/github_service.py` -> `app/adapters/integrations/github/service.py`
- `app/services/hubspot_service.py` -> `app/adapters/integrations/hubspot/service.py`
- `app/services/notion_service.py` -> `app/adapters/integrations/notion/service.py`
- `app/services/stripe_service.py` -> `app/adapters/integrations/stripe/service.py`

## Day 1 Outcome

After day 1:

- the target architecture is documented,
- the package skeleton exists,
- the highest-impact service files have an agreed target destination,
- new code should follow the new placement rules.

No runtime code movement is required for day 1 beyond compatibility-safe extraction work.
