# Codebase Map

## Layer Architecture

```
[Client]  -->  [API / Web Routes]  -->  [Service Layer]  -->  [Models / DB]
                     |                       |
                  [RBAC]              [Engines / Tools]
                     |                       |
                  [Audit]             [Platform: Signals, Decisions, Dead-letter]
```

---

## API Layer (`app/api/v1/endpoints/`)

**Responsibility:** HTTP request/response handling, input validation, RBAC enforcement, response serialization.

**Rules:**
- Routes must be thin — no business logic in endpoint functions
- All mutating endpoints require `require_roles()` dependency
- Use Pydantic schemas for request/response models
- Record audit events via `record_action()` after writes

**Key files:** 62+ endpoint files organized by feature domain.

| Group | Files | Description |
|-------|-------|-------------|
| Auth & Users | `auth.py`, `users.py`, `orgs.py`, `api_keys.py` | Authentication, user management |
| Operations | `tasks.py`, `projects.py`, `goals.py`, `approvals.py` | Core business operations |
| Integrations | `integrations.py` + 13 specific files | External service connections |
| Automation | `automation.py`, `executions.py` | Triggers, workflows, execution |
| Intelligence | `agents.py`, `decision_cards.py`, `workflow_observability.py` | AI agents, analytics |
| Admin | `admin.py`, `health.py`, `observability.py` | System management |

---

## Services (`app/services/`)

**Responsibility:** ALL business logic. Database operations, external API orchestration, policy enforcement, notification dispatch.

**Rules:**
- Services own the business rules
- Services call Tools (HTTP clients) for external APIs
- Services call Models for database operations
- Services emit Signals for cross-cutting concerns
- Services never import from API layer

**Key modules (90+):**

| Category | Files | Purpose |
|----------|-------|---------|
| Core | `user.py`, `organization.py`, `approval.py` | User/org management, approval workflows |
| Execution | `execution_engine.py`, `orchestrator.py` | Action execution, multi-step orchestration |
| Memory | `memory.py`, `clone_memory.py`, `embedding.py` | AI context building, semantic search; `memory.consolidate_profile_memory_duplicates` for engine-safe consolidation |
| Observability | `ai_call_log.py` | AI call metrics (latency, tokens); brain router delegates here so engines do not mutate DB |
| AI | `ai_router.py`, `clone_brain.py`, `confidence.py` | Provider dispatch, brain logic |
| Integration | `gmail_service.py`, `slack_service.py`, etc. | Per-integration DB + sync logic |
| Workflow | `automation.py`, `workflow_insights.py` | Trigger/workflow management, analytics |
| Policy | `autonomy_policy.py`, `policy_service.py` | Autonomy levels, action policies |
| Learning | `self_learning.py`, `conversation_learning.py` | Feedback loops, learning extraction |

---

## Engines (`app/engines/`)

**Responsibility:** Specialized processing pipelines that combine multiple services into higher-order operations.

| Engine | Location | Purpose |
|--------|----------|---------|
| **Brain** | `app/engines/brain/` | LLM routing, workflow planning, prompt engineering, confidence scoring |
| **Decision** | `app/engines/decision/` | Audit-grade decision recording, workflow policy enforcement |
| **Execution** | `app/engines/execution/` | Workflow step runtime, handler dispatch, retry/recovery, idempotency |
| **Intelligence** | `app/engines/intelligence/` | Knowledge extraction, memory consolidation, entity graph, projections |

---

## Workflows

**Definition:** `app/models/workflow_definition.py` — Template with steps, trigger mode, risk level.

**Runtime:** `app/models/workflow_run.py` — Execution instance with status tracking.

**Step execution:** `app/engines/execution/workflow_handlers.py` — Action handlers (send_email, send_slack, create_task, ai_generate, http_request, wait, noop).

**Flow:**
```
WorkflowDefinition (template)
  --> WorkflowRun (execution instance)
    --> WorkflowStepRun (per-step with latency_ms, status)
      --> Approval (if step requires_approval)
        --> Execution (actual side effect)
```

---

## Approvals (`app/models/approval.py`)

**Responsibility:** Human-in-the-loop safety gate for risky operations.

**Flow:**
1. Service creates Approval with `type`, `risk_level`, `payload_json`
2. CEO/ADMIN reviews in UI or API
3. Approval accepted with note → Execution created
4. Execution engine runs the approved action
5. Audit event recorded

**Types:** `send_message`, `execute_workflow`, `delete_resource`, `integration_action`, etc.

---

## Observability

| Component | Location | Purpose |
|-----------|----------|---------|
| Audit Log | `app/logs/audit.py` | Immutable event trail for all mutations |
| Signals | `app/platform/signals/` | Event pub/sub (publisher, consumers, topics) |
| Decisions | `app/platform/decisions/` | AI decision recording with confidence + rationale |
| Dead Letter | `app/platform/dead_letter/` | Failed operation capture for retry/inspection |
| Telemetry | `app/core/telemetry.py` | OpenTelemetry tracing |
| Health | `app/api/v1/endpoints/health.py` | System health checks |

---

## Models (`app/models/`)

**Responsibility:** SQLAlchemy ORM models. Define database schema and relationships.

**60+ models** organized by domain:

| Domain | Key Models |
|--------|------------|
| Auth | `User`, `Organization`, `Workspace`, `OrgMembership`, `ApiKey` |
| Operations | `Project`, `Task`, `Goal`, `Approval`, `Execution` |
| Communication | `Email`, `SlackMessage`, `WhatsAppMessage` |
| CRM | `Contact`, `Employee`, `LeadRoutingRule` |
| Workflow | `WorkflowDefinition`, `WorkflowRun`, `WorkflowStepRun` |
| Intelligence | `AiCallLog`, `DecisionCard`, `DecisionTrace`, `CoachingReport` |
| Platform | `Signal`, `ThreatSignal`, `DeadLetterEntry`, `DecisionLog` |
| Memory | `ProfileMemory`, `DailyContext`, `CloneMemoryEntry`, `MemoryEmbedding` |

---

## Schemas (`app/schemas/`)

**Responsibility:** Pydantic models for API input validation and response serialization.

**Rules:**
- One schema file per feature domain
- `*Create` schemas for POST input
- `*Read` schemas for GET responses
- `*Update` schemas for PATCH input
- Never expose internal model fields (e.g., hashed passwords)

---

## Tests (`tests/`)

**208 test files, 1986+ passing tests.**

**Stack:** pytest + pytest-asyncio, in-memory SQLite, monkeypatch for mocking.

**Conventions:**
- `conftest.py` provides `db` (async session) and `client` (httpx AsyncClient) fixtures
- `_make_auth_headers()` creates JWT headers for API tests
- Monkeypatch services at the source module, not the importer
- Feature flags toggled via `monkeypatch.setattr(settings, "FEATURE_XXX", True/False)`
