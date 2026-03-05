# C4 Architecture - Nidin BOS

This document describes the current architecture of AI BOS using a C4-style view:

1. System Context
2. Container Diagram
3. Component Diagram
4. Key Runtime Sequences

Source of truth for implementation is the code under `app/`, `run_scheduler.py`, and `run_webhook_worker.py`.

## 1) System Context

```mermaid
flowchart LR
    CEO[CEO/Admin/Manager/Staff User]
    APIConsumer[API Consumer / External Client]
    BOS[Nidin BOS Platform]

    subgraph External Systems
      LLMs[OpenAI / Anthropic / Groq / Gemini]
      Providers[Google, GitHub, ClickUp, Slack, WhatsApp, Notion, Stripe, HubSpot, LinkedIn, GA, Calendly, ElevenLabs, DigitalOcean]
      WebhookTargets[Customer Webhook Endpoints]
    end

    CEO -->|Web UI + Session| BOS
    APIConsumer -->|Bearer/API Key| BOS
    BOS -->|LLM Calls| LLMs
    BOS -->|Sync + Actions| Providers
    BOS -->|Signed Event Delivery| WebhookTargets
```

### Context Notes
- End users interact through server-rendered web pages and JS clients.
- Programmatic clients use API routes with bearer JWT or scoped API keys.
- AI BOS orchestrates AI calls, business workflows, integrations, approvals, and governance controls.

## 2) Container Diagram

```mermaid
flowchart TB
    User[Browser User]
    Client[API Client]
    DB[(PostgreSQL / SQLite)]
    Redis[(Redis Optional)]
    Providers[External Providers]
    WebhookTargets[Webhook Receivers]

    subgraph BOS Deployment
      App[FastAPI App\nAPI + Web + Middleware]
      Scheduler[Scheduler Process\nrun_scheduler.py]
      Worker[Webhook Worker\nrun_webhook_worker.py]
    end

    User -->|/web/*| App
    Client -->|/api/v1/*| App
    App --> DB
    App --> Redis
    App --> Providers
    App -->|enqueue/send webhook| DB
    Worker -->|retry dispatch| DB
    Worker --> WebhookTargets
    Scheduler -->|periodic sync/maintenance| DB
    Scheduler --> Providers
```

### Container Responsibilities
- FastAPI App:
  - Auth, RBAC, routing, rendering, business services, audit, AI orchestration.
- Scheduler:
  - Periodic integration sync, trend updates, maintenance jobs, SLA/summary routines.
- Webhook Worker:
  - Retries failed deliveries from DB queue/logs.
- DB:
  - Domain state, snapshots, approvals, memory, events, integrations, governance.
- Redis (optional):
  - Rate-limit/idempotency/support caches.

## 3) Component Diagram (Inside FastAPI App)

```mermaid
flowchart LR
    MW[Middleware Layer\nSecurityHeaders, CorrelationID,\nRateLimit, BodyLimit, RequestLog]
    Web[Web Routers\nweb/auth.py, web/pages.py, web/chat.py]
    API[API Routers\napi/v1/endpoints/*]
    Deps[Auth/RBAC/Deps\ncore/deps.py, core/rbac.py]
    Services[Service Layer\nmemory, ai_router, approvals,\nexecution, integrations, governance,\ncompliance, workspace, webhook]
    Agents[Agent Orchestrator\nagents/orchestrator.py]
    Models[SQLAlchemy Models]
    DB[(DB)]
    Tools[Provider Tools\napp/tools/*]
    Audit[Audit/Events\nlogs/audit.py]

    MW --> Web
    MW --> API
    Web --> Deps
    API --> Deps
    Web --> Services
    API --> Services
    Services --> Agents
    Services --> Tools
    Services --> Models
    Services --> Audit
    Models --> DB
```

### Major Components and Code Mapping
- App bootstrap and startup guards:
  - `app/main.py`
- Middleware:
  - `app/core/middleware.py`
- Auth, deps, RBAC:
  - `app/core/deps.py`
  - `app/core/rbac.py`
  - `app/core/security.py`
- API router composition:
  - `app/api/v1/router.py`
- Web routes:
  - `app/web/auth.py`
  - `app/web/pages.py`
  - `app/web/chat.py`
- Agent orchestration:
  - `app/agents/orchestrator.py`
- AI provider abstraction:
  - `app/services/ai_router.py`
- Approval + execution control:
  - `app/api/v1/endpoints/approvals.py`
  - `app/services/approval.py`
  - `app/services/execution_engine.py`
- Integration and webhook subsystems:
  - `app/api/v1/endpoints/integrations.py`
  - `app/services/integration.py`
  - `app/services/webhook.py`
- Memory/workspace subsystems:
  - `app/services/memory.py`
  - `app/api/v1/endpoints/memory.py`
  - `app/services/workspace.py`
  - `app/api/v1/endpoints/workspaces.py`
- Governance/compliance:
  - `app/services/compliance_engine.py`
  - `app/api/v1/endpoints/control/ceo.py`
- Data model registration:
  - `app/models/registry.py`

## 4) Key Runtime Sequences

### 4.1 Login + Session

```mermaid
sequenceDiagram
    participant U as User
    participant W as /web/login
    participant H as web/_helpers.authenticate_user
    participant D as DB
    participant A as Audit

    U->>W: POST username/password(+totp)
    W->>H: authenticate_user(...)
    H->>D: Load user + verify password/MFA
    H->>A: record login_success/login_failed
    W-->>U: Set pc_session + pc_csrf cookies
```

### 4.2 Talk Request + Memory + Agent Routing

```mermaid
sequenceDiagram
    participant U as User
    participant C as /web/agents/chat
    participant M as Memory Service
    participant B as Brain Context Builder
    participant O as Agent Orchestrator
    participant R as AI Router
    participant L as LLM Provider
    participant D as DB

    U->>C: message + avatar_mode
    C->>M: build memory context
    C->>B: build brain context
    C->>O: run_agent(...)
    O->>R: call_ai(...)
    R->>L: provider request/fallback
    L-->>R: response
    R-->>O: response text
    O-->>C: role + actions + confidence
    C->>D: persist chat + learning
    C-->>U: JSON chat response
```

### 4.3 Approval Request -> Approve -> Execute

```mermaid
sequenceDiagram
    participant U as Manager/CEO
    participant AP as /api/v1/approvals/*
    participant AS as approval service
    participant EX as execution engine
    participant D as DB
    participant A as audit/events
    participant T as tool/provider action

    U->>AP: request approval
    AP->>AS: create pending approval
    AS->>D: save approval
    AP->>A: approval_requested

    U->>AP: approve
    AP->>AS: atomic approve update
    AS->>D: mark approved

    AP->>EX: execute_approval(...)
    EX->>D: idempotent claim + execution row
    EX->>T: perform action handler
    EX->>A: execution_started/succeeded/failed
```

### 4.4 Integration Sync + Dashboard Read Model

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant I as integration services
    participant P as Providers
    participant D as DB
    participant UI as Dashboard (/)

    S->>I: periodic sync per org
    I->>P: fetch remote data
    I->>D: upsert snapshots/signals/metrics

    UI->>D: load KPIs + layers + briefings
    UI-->>User: rendered dashboard
```

## Deployment Boundaries

- HTTP app runtime:
  - FastAPI app in `app/main.py`
- Separate process for scheduler:
  - `run_scheduler.py`
- Separate process for webhook retries:
  - `run_webhook_worker.py`

Production guidance and checks:
- `docs/PRODUCTION_RUNBOOK.md`
- `scripts/check_ready.py`

## Design Characteristics

- Style: modular monolith with clear service boundaries.
- Data consistency: SQL transaction boundaries in service methods; idempotency guards on critical flows.
- Safety:
  - RBAC and org scoping in dependency layer.
  - Approval gates for risky actions.
  - Auditable event trail and webhook delivery logs.
- Extensibility:
  - New endpoints by domain module.
  - New provider via `tools/*` + `services/*` + integration endpoint.
  - New agent behavior through orchestrator role/prompt routing.
