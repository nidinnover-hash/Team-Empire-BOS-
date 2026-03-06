# Nidin BOS - Next Phase Architecture Plan

## 1. Executive Summary

BOS has reached a mature modular monolith state: 305 Python files, 71 models, 104 services, 4 engine modules (brain/decision/execution/intelligence), a signal+decision platform layer, 27 SSR pages, and full RBAC/approval/audit infrastructure. The next phase transforms BOS from an "intelligent assistant with integrations" into a **full AI business automation platform** through three vectors:

1. **Visual workflow builder** — let users create automations without code
2. **Knowledge brain upgrade** — semantic memory + RAG intelligence loop
3. **Operational reliability hardening** — dead-letter, retry, failure inspection

The architecture is ready. `app/engines/`, `app/domains/automation/`, `app/platform/signals/`, and `app/application/automation/` already exist as landing zones. The critical constraint is **no destabilization** — every change must preserve the 1873-test green suite, existing endpoint contracts, and SSR page behavior.

---

## 2. Top 5 Highest ROI Modules

| # | Module | Impact | Effort | Landing Zone |
|---|--------|--------|--------|-------------|
| 1 | **Visual Workflow Builder** | Turns BOS from dev tool to user product | High | `app/domains/automation/`, `app/templates/automations.html`, `app/static/js/automations-page.js` |
| 2 | **AI Workflow Copilot** | Natural language -> workflow plan -> approval -> execution | Medium | `app/engines/decision/workflow_plans.py` (exists), new `app/engines/brain/workflow_copilot.py` |
| 3 | **Dead-Letter + Retry Layer** | Zero lost jobs, inspectable failures | Medium | `app/platform/dead_letter/`, `app/engines/execution/retry.py` |
| 4 | **Executive Analytics Dashboard** | CEO-grade operational intelligence | Medium | `app/engines/intelligence/`, `app/api/v1/endpoints/intelligence.py` (exists), dashboard widgets |
| 5 | **Knowledge Brain v2** | pgvector is live; add RAG pipeline, memory consolidation, knowledge graph | Medium | `app/services/embedding.py` (exists), new `app/engines/intelligence/knowledge.py` |

---

## 3. Recommended Implementation Order

### Phase 1: Foundation (Days 1-30)

**1a. Dead-Letter Queue + Retry Infrastructure**
- New: `app/platform/dead_letter/` (store, inspector, reprocessor)
- Modify: `app/engines/execution/workflow_runtime.py` — wrap handler dispatch in dead-letter capture
- Modify: `app/services/sync_scheduler.py` — failed jobs write to dead-letter instead of log-and-forget
- Modify: `app/services/webhook.py` — failed deliveries enter dead-letter
- New model: `DeadLetterEntry` (org_id, source_type, source_id, payload, error, attempts, status, created_at, resolved_at)
- New API: `GET /api/v1/control/dead-letter` (CEO/ADMIN), `POST /api/v1/control/dead-letter/{id}/retry`
- New web widget: dead-letter count on health page
- Feature flag: `DEAD_LETTER_ENABLED`

**1b. Workflow Builder Backend**
- Extend: `app/domains/automation/models.py` — add `steps` JSON field, `trigger_type`, `trigger_config`
- Extend: `app/domains/automation/service.py` — CRUD for workflow definitions with step validation
- New: `app/engines/execution/step_executor.py` — execute individual workflow steps (send_email, create_task, call_ai, http_request, wait, branch)
- Extend: `app/engines/execution/workflow_runtime.py` — step-by-step execution with state tracking
- New schema: `WorkflowStepSchema` (type, config, on_success, on_failure)
- API: extend `app/api/v1/endpoints/automation.py` with step CRUD

**1c. Workflow Builder Frontend**
- Rewrite: `app/static/js/automations-page.js` — visual step builder (drag-and-drop step cards, condition branches, trigger config)
- Rewrite: `app/templates/automations.html` — builder canvas layout
- Keep SSR shell, enhance with vanilla JS builder components
- No framework change — vanilla JS + Jinja SSR

### Phase 2: Intelligence (Days 30-60)

**2a. AI Workflow Copilot**
- New: `app/engines/brain/workflow_copilot.py`
  - `plan_workflow(natural_language_description, org_context) -> WorkflowPlan`
  - Uses existing `app/engines/decision/workflow_plans.py` for plan structure
  - Outputs a `WorkflowDefinition` draft that lands in approval queue
- Integration: Talk page gets a "Build automation" command
- Integration: Automations page gets "Describe what you want" input
- All generated workflows require approval before activation (existing approval flow)

**2b. Knowledge Brain v2**
- New: `app/engines/intelligence/knowledge.py`
  - `consolidate_memories(org_id)` — merge duplicate/overlapping profile memories
  - `extract_knowledge(conversation_history) -> list[KnowledgeEntry]` — extract facts from conversations
  - `build_knowledge_graph(org_id)` — entity relationships from memory + contacts + integrations
- Extend: `app/services/embedding.py` — batch embedding for historical data backfill
- New job: `app/jobs/intelligence.py` — nightly knowledge consolidation
- Modify: `build_memory_context_semantic()` — use knowledge graph for context ranking

**2c. Executive Analytics Layer**
- Extend: `app/engines/intelligence/projections.py` — add trend projections, anomaly detection
- New: `app/engines/intelligence/executive_metrics.py` — aggregate KPIs across all domains
- Extend: `app/api/v1/endpoints/dashboard_kpi.py` — new `/api/v1/dashboard/executive` endpoint
- Extend: `app/static/js/dashboard-page.js` — executive summary widget with charts
- Signal-driven: subscribe to all domain signals for real-time metric updates

### Phase 3: Platform (Days 60-90)

**3a. Automation Template Marketplace**
- New: `app/domains/automation/templates.py` — template registry, import/export
- Extend: `app/models/workflow_template.py` (exists) — add `category`, `tags`, `install_count`, `source` (builtin/community/custom)
- New API: `GET /api/v1/automation/templates`, `POST /api/v1/automation/templates/{id}/install`
- New: `app/static/js/template-gallery.js` — browse and install templates
- Ship 10 built-in templates: daily briefing, lead follow-up, invoice reminder, PR review, meeting prep, expense report, weekly digest, onboarding checklist, social post schedule, incident response

**3b. Approval Safety Hardening**
- Extend: `app/services/approval.py` — add `approval_policy` field (auto-approve if confidence > threshold, escalate to specific role, require multi-approval)
- New: `app/engines/decision/approval_policies.py` — policy evaluation engine
- Extend: `app/models/approval.py` — add `policy_id`, `escalation_chain`, `auto_approved_reason`
- Signal: `approval.auto_approved`, `approval.escalated`

**3c. Progressive UX Enhancement**
- Add: real-time updates via SSE (Server-Sent Events) for workflow runs, approvals, dead-letter
- New: `app/api/v1/endpoints/sse.py` — SSE endpoint per page
- Extend: `app/static/js/ui-utils.js` — SSE client helper
- No SPA migration — SSE + vanilla JS progressive enhancement

---

## 4. Target Module Boundaries

```
app/
  engines/
    brain/
      router.py            (existing - AI provider routing)
      drafting.py           (existing - agent orchestration)
      workflow_copilot.py   (NEW - NL -> workflow plan)
      confidence.py         (existing)
    decision/
      workflow_plans.py     (existing - plan structure)
      workflow_policy.py    (existing - execution policies)
      approval_policies.py  (NEW - approval policy engine)
    execution/
      workflow_runtime.py   (existing - extend with step execution)
      workflow_handlers.py  (existing)
      step_executor.py      (NEW - individual step execution)
      retry.py              (NEW - retry strategy)
    intelligence/
      projections.py        (existing)
      knowledge.py          (NEW - knowledge brain v2)
      executive_metrics.py  (NEW - CEO analytics)

  domains/
    automation/
      models.py             (existing - extend with steps)
      service.py            (existing - extend CRUD)
      repo.py               (existing)
      events.py             (existing)
      templates.py          (NEW - template registry)

  platform/
    signals/                (existing - no changes needed)
    decisions/              (existing - no changes needed)
    dead_letter/            (NEW)
      __init__.py
      store.py              (dead-letter storage)
      inspector.py          (query/filter dead-letter entries)
      reprocessor.py        (retry logic)

  application/
    automation/
      use_cases.py          (existing - extend)
      bootstrap.py          (existing)
```

---

## 5. Integration Map

### How each capability integrates:

#### Visual Workflow Builder
- **engines**: `execution/step_executor.py` executes steps, `execution/workflow_runtime.py` orchestrates
- **application**: `automation/use_cases.py` — CreateWorkflow, UpdateWorkflow, ActivateWorkflow
- **domains**: `automation/models.py` — WorkflowDefinition with steps JSON
- **platform/signals**: emits `workflow.created`, `workflow.activated`, `workflow.step.completed`, `workflow.step.failed`
- **adapters**: step_executor calls adapters for external actions (send email, create GitHub issue, etc.)
- **web/templates**: `automations.html` — builder canvas
- **api**: `automation.py` — CRUD + activation endpoints

#### AI Workflow Copilot
- **engines**: `brain/workflow_copilot.py` generates plans, `decision/workflow_plans.py` structures them
- **application**: new `PlanWorkflowFromNaturalLanguage` use case
- **domains**: outputs a `WorkflowDefinition` draft
- **platform/signals**: emits `workflow.planned`, `workflow.plan.approved`
- **web**: Talk page command + automations page input
- **api**: `POST /api/v1/automation/plan` (accepts natural language, returns draft)

#### Dead-Letter Queue
- **engines**: `execution/retry.py` — retry strategy (exponential backoff, max attempts)
- **platform**: `dead_letter/store.py` writes entries, `reprocessor.py` retries
- **signals**: subscribes to `execution.failed`, `webhook.delivery.failed`, `scheduler.job.failed`
- **web**: health page widget showing dead-letter count
- **api**: `control/dead-letter` endpoints

#### Executive Analytics
- **engines**: `intelligence/executive_metrics.py` aggregates across domains
- **platform/signals**: subscribes to all domain signals for real-time counters
- **web**: dashboard executive summary widget
- **api**: `dashboard_kpi.py` extended endpoints

#### Knowledge Brain v2
- **engines**: `intelligence/knowledge.py` — consolidation, extraction, graph
- **services**: `embedding.py` (exists) — batch operations
- **platform/signals**: subscribes to `memory.updated` for re-embedding
- **jobs**: nightly consolidation job
- **web**: Talk page benefits automatically (semantic context)

---

## 6. Migration Strategy from Service-Heavy State

### Principle: Strangler Fig Pattern

Services remain as stable facades. New logic goes into engines/domains/application. Services delegate to new code over time.

### Concrete steps:

1. **New capabilities** → always land in `engines/`, `domains/`, or `application/`
2. **Existing services called by new code** → keep calling them (they're stable interfaces)
3. **Services that grow new logic** → extract to engine, leave service as thin wrapper
4. **Services that are pure CRUD** → leave alone (not worth migrating)
5. **Services that are compatibility wrappers** (`ai_router.py`, `orchestrator.py`) → keep as-is

### What NOT to migrate (stable, not worth the risk):
- `sync_scheduler.py` (1064 LOC but stable, well-tested)
- `email_service.py` (959 LOC, integration-heavy)
- `memory.py` (869 LOC, just enhanced with semantic)
- All integration services (`github_service.py`, `slack_service.py`, etc.)

### What TO migrate incrementally:
- Workflow execution logic → already in `engines/execution/`
- Decision logic → already in `engines/decision/`
- AI routing → already in `engines/brain/`
- Intelligence/analytics → into `engines/intelligence/`

---

## 7. Backward Compatibility Strategy

| Area | Strategy |
|------|----------|
| **API endpoints** | Never remove, only add. Deprecate with `X-Deprecated` header. |
| **Service functions** | Keep signatures stable. New params are keyword-only with defaults. |
| **Models** | Only add columns (nullable or with defaults). Never drop columns in-phase. |
| **Templates** | Extend, never replace. New sections added via Jinja blocks. |
| **JS** | Page scripts are independent. New capabilities added as new functions. |
| **Signals** | New topics added freely. Never change existing topic strings. |
| **Config** | New settings always have safe defaults. Feature flags gate new behavior. |

---

## 8. Risk Analysis

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Workflow step executor runs arbitrary actions** | HIGH | All workflow activations require approval. Steps execute through existing permission-checked service functions. No raw shell/SQL execution. |
| **AI copilot generates invalid workflows** | MEDIUM | Generated workflows enter draft state, require human review + approval before activation. Validate step schema before saving. |
| **Dead-letter queue grows unbounded** | MEDIUM | Auto-archive entries older than 30 days. Dashboard alert when queue exceeds threshold. |
| **pgvector embedding costs (OpenAI API)** | LOW | Fire-and-forget, graceful degradation. Falls back to lexical search. Rate limit embedding calls per org. |
| **SSE connections exhaust server resources** | MEDIUM | Connection timeout (5 min), per-org connection limit, graceful fallback to polling. |
| **Migration collision** | LOW | Alembic revision chain is linear. Each phase gets its own migration batch. |
| **Workflow builder JS complexity** | MEDIUM | Keep vanilla JS. No framework adoption. Component pattern with clean separation. |

---

## 9. Required Feature Flags

```python
# Phase 1
DEAD_LETTER_ENABLED: bool = True
WORKFLOW_BUILDER_ENABLED: bool = True
WORKFLOW_MAX_STEPS: int = 20
WORKFLOW_MAX_ACTIVE_PER_ORG: int = 50

# Phase 2
WORKFLOW_COPILOT_ENABLED: bool = True
KNOWLEDGE_CONSOLIDATION_ENABLED: bool = True
EXECUTIVE_ANALYTICS_ENABLED: bool = True

# Phase 3
AUTOMATION_TEMPLATES_ENABLED: bool = True
APPROVAL_POLICIES_ENABLED: bool = True
SSE_ENABLED: bool = True
SSE_MAX_CONNECTIONS_PER_ORG: int = 10
```

---

## 10. Required Database Changes

### Phase 1
```
ALTER TABLE workflow_definitions ADD COLUMN steps JSONB DEFAULT '[]';
ALTER TABLE workflow_definitions ADD COLUMN trigger_type VARCHAR(30);
ALTER TABLE workflow_definitions ADD COLUMN trigger_config JSONB DEFAULT '{}';
ALTER TABLE workflow_runs ADD COLUMN current_step_index INTEGER DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN step_results JSONB DEFAULT '[]';

CREATE TABLE dead_letter_entries (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    source_type VARCHAR(30) NOT NULL,  -- 'workflow', 'webhook', 'scheduler', 'signal'
    source_id VARCHAR(100),
    payload JSONB NOT NULL,
    error_message TEXT,
    error_traceback TEXT,
    attempts INTEGER DEFAULT 1,
    max_attempts INTEGER DEFAULT 3,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, retrying, resolved, archived
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    INDEX ix_dead_letter_org_status (organization_id, status)
);
```

### Phase 2
```
CREATE TABLE knowledge_entries (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    workspace_id INTEGER REFERENCES workspaces(id) ON DELETE SET NULL,
    entity_type VARCHAR(30),  -- 'person', 'company', 'concept', 'process', 'decision'
    entity_name VARCHAR(200),
    fact_text TEXT NOT NULL,
    confidence FLOAT DEFAULT 0.7,
    source_type VARCHAR(30),  -- 'conversation', 'memory', 'integration', 'manual'
    source_id INTEGER,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE workflow_templates ADD COLUMN category VARCHAR(50);
ALTER TABLE workflow_templates ADD COLUMN tags JSONB DEFAULT '[]';
ALTER TABLE workflow_templates ADD COLUMN install_count INTEGER DEFAULT 0;
ALTER TABLE workflow_templates ADD COLUMN source VARCHAR(20) DEFAULT 'custom';
```

### Phase 3
```
CREATE TABLE approval_policies (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    policy_type VARCHAR(30),  -- 'auto_approve', 'require_role', 'multi_approve', 'escalate'
    config JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE approvals ADD COLUMN policy_id INTEGER REFERENCES approval_policies(id);
ALTER TABLE approvals ADD COLUMN auto_approved_reason TEXT;
```

---

## 11. Testing Strategy

| Layer | Strategy |
|-------|----------|
| **Step executor** | Unit test each step type with mocked adapters. Parameterized tests for all step types. |
| **Workflow runtime** | Integration tests: create definition -> activate -> run -> verify step results. |
| **Dead-letter** | Unit: store/retrieve/retry. Integration: trigger failure -> verify entry created. |
| **AI copilot** | Mock AI response. Verify generated workflow validates against schema. |
| **Knowledge brain** | Mock embeddings. Test consolidation logic. Test graph construction. |
| **Executive analytics** | Test aggregation queries. Mock signal data. Verify KPI calculations. |
| **Workflow builder UI** | Manual testing + screenshot regression. No E2E framework change. |
| **SSE** | Test connection lifecycle. Test event delivery. Test graceful disconnection. |
| **Approval policies** | Parameterized tests for each policy type. Test escalation chains. |

**Test count target**: +200 tests across all phases (total ~2073).

---

## 12. Definition of Done per Phase

### Phase 1 (Days 1-30)
- [ ] Dead-letter queue captures all failed executions, webhooks, and scheduler jobs
- [ ] Dead-letter API returns entries filtered by status/source
- [ ] Dead-letter retry re-executes and clears on success
- [ ] Workflow builder saves multi-step definitions with triggers
- [ ] Step executor handles: send_email, create_task, call_ai, http_request, wait, branch
- [ ] Workflow runs track step-by-step progress
- [ ] Automations page shows visual step builder
- [ ] 60+ new tests, full suite green
- [ ] Feature flags gate all new behavior

### Phase 2 (Days 30-60)
- [ ] AI copilot accepts natural language, outputs valid workflow draft
- [ ] Generated workflows require approval before activation
- [ ] Knowledge consolidation runs nightly, merges duplicates
- [ ] Knowledge extraction identifies facts from conversations
- [ ] Executive dashboard shows cross-domain KPI summary
- [ ] Trend projections show 7-day/30-day directional indicators
- [ ] 70+ new tests, full suite green

### Phase 3 (Days 60-90)
- [ ] 10 built-in workflow templates available for install
- [ ] Template gallery UI with categories and search
- [ ] Approval policies configurable per workflow
- [ ] Auto-approve works for high-confidence, low-risk actions
- [ ] SSE delivers real-time updates to automations and health pages
- [ ] 70+ new tests, full suite green
- [ ] All new capabilities emit signals and are observable

---

## 13. Top 10 Anti-Patterns to Avoid

1. **Don't adopt a JS framework.** Vanilla JS + Jinja SSR is the architecture. Adding React/Vue creates a parallel rendering pipeline.

2. **Don't create new service files for engine logic.** New business logic goes in `engines/`, `domains/`, or `application/`. Services are facades and compatibility wrappers.

3. **Don't skip approval for AI-generated workflows.** Every generated workflow MUST enter the approval queue. No auto-activation.

4. **Don't add raw SQL execution steps.** Workflow steps call typed service functions. No arbitrary query execution from user-defined workflows.

5. **Don't break the signal contract.** Never rename existing signal topics. Only add new ones. Consumers must handle unknown topics gracefully.

6. **Don't bypass org scoping.** Every new model, query, and API endpoint MUST filter by `organization_id`. No cross-org data leakage.

7. **Don't create god-objects in engines.** Each engine module should have single-responsibility files. `workflow_runtime.py` orchestrates; `step_executor.py` executes; `retry.py` retries.

8. **Don't couple the builder UI to specific step implementations.** The builder should work with a step registry (type -> schema -> renderer). Adding a new step type should not require modifying the builder core.

9. **Don't store workflow state in memory.** All workflow run state must be in the database. Server restarts must not lose in-progress workflows.

10. **Don't add blocking I/O in signal consumers.** Signal handlers must be async and non-blocking. Heavy work goes into background tasks via `asyncio.create_task()`.

---

## 14. 30/60/90 Day Sequence

### Days 1-10: Dead-Letter + Workflow Model
- Dead-letter model, store, API
- Workflow definition steps field migration
- Step schema validation
- Wire dead-letter into webhook + scheduler failures

### Days 11-20: Step Executor + Builder Backend
- Step executor for 6 core step types
- Workflow runtime step-by-step execution
- Workflow activation + trigger system
- Integration tests for full workflow lifecycle

### Days 21-30: Builder Frontend + Polish
- Automations page visual builder
- Step card components (drag, configure, connect)
- Trigger configuration UI
- Dead-letter widget on health page
- Phase 1 test suite complete

### Days 31-40: AI Copilot
- `workflow_copilot.py` with prompt engineering
- Talk page "build automation" command
- Automations page NL input
- Copilot output -> workflow draft -> approval queue

### Days 41-50: Knowledge Brain v2
- Knowledge extraction from conversations
- Memory consolidation (merge duplicates, boost confident entries)
- Batch embedding backfill for historical data
- Nightly consolidation job

### Days 51-60: Executive Analytics
- Cross-domain KPI aggregation
- Dashboard executive summary widget
- Trend projections (7d/30d)
- Phase 2 test suite complete

### Days 61-70: Templates + Marketplace
- Template model extensions
- 10 built-in templates
- Template gallery UI
- Import/install flow

### Days 71-80: Approval Policies + Safety
- Approval policy model + engine
- Auto-approve for low-risk, high-confidence
- Escalation chains
- Multi-approval support

### Days 81-90: SSE + Polish
- SSE endpoint for real-time updates
- Wire into automations, health, approvals pages
- Performance profiling under load
- Phase 3 test suite complete
- Full documentation update
