# Nidin BOS — Project Context

## What is Nidin BOS?

Nidin BOS (Business Operating System) is an AI-powered operations platform built as a FastAPI modular monolith. It serves as a unified command center for managing business operations across multiple companies through AI agents, workflow automation, and intelligent decision support.

## System Purpose

- Autonomous work operations with human-in-the-loop safety controls
- Task orchestration across multiple integrations (Gmail, Slack, GitHub, HubSpot, Stripe, etc.)
- Intelligent decision support with confidence scoring and approval workflows
- Memory-augmented AI agents that learn from past interactions
- Real-time observability, audit trails, and compliance guardrails

## Companies Supported

| Company | Domain | Role |
|---------|--------|------|
| Empire Overseas Education (EmpireO) | International education consulting | Primary business |
| ESA (Empire Student Assistance) | Student support services | Support arm |
| Empire Digital | Digital marketing and web services | Digital division |
| Codnov / Nidin.Ai | AI platform development | Tech company |

## Architecture: FastAPI Modular Monolith

```
Browser / API Client
    |
FastAPI (app/main.py)
    |
Middleware Stack (security headers, rate limiting, CORS, compression)
    |
API Routes (app/api/v1/endpoints/)   +   Web Routes (app/web/)
    |                                          |
RBAC Guard (app/core/rbac.py)         Session Cookie Auth
    |
Service Layer (app/services/)  <-- ALL business logic lives here
    |
+-- Models (app/models/)       -- SQLAlchemy ORM, PostgreSQL
+-- Engines (app/engines/)     -- Brain, Decision, Execution, Intelligence
+-- Tools (app/tools/)         -- Pure async HTTP clients (no DB)
+-- Platform (app/platform/)   -- Signals, Decisions, Dead-letter
+-- Jobs (app/jobs/)           -- Background tasks, schedulers
```

## Main Engines

| Engine | Location | Purpose |
|--------|----------|---------|
| Brain | `app/engines/brain/` | Workflow planning, LLM routing, context building, confidence scoring |
| Decision | `app/engines/decision/` | Audit-grade decision recording, workflow policy enforcement |
| Execution | `app/engines/execution/` | Workflow runtime, step handlers, retry/recovery, idempotency |
| Intelligence | `app/engines/intelligence/` | Knowledge extraction, memory consolidation, projections |

## High-Level Folder Structure

```
app/
  api/v1/endpoints/     62+ API endpoint files
  application/          Use cases and orchestration layer
  adapters/             AI and integration adapters
  agents/               Agent orchestration
  core/                 Config, RBAC, security, middleware, deps
  db/                   Database session factory, ORM base
  domains/              Domain-driven design bounded contexts
  engines/              Brain, Decision, Execution, Intelligence
  jobs/                 Background tasks (approval, maintenance, monitoring)
  logs/                 Audit trail recording
  memory/               Semantic memory retrieval
  models/               60+ SQLAlchemy ORM models
  platform/             Signals, Decisions, Dead-letter queue
  schemas/              47+ Pydantic validation schemas
  services/             90+ business logic modules
  static/               CSS (25), JS (51), assets
  templates/            36 Jinja2 HTML templates
  tools/                Pure async HTTP clients per integration
  web/                  Web routes (auth, pages, chat)
alembic/                84 database migrations
tests/                  208 test files, 1986+ passing tests
deploy/                 Systemd, Nginx, setup scripts
scripts/                45+ utility and deployment scripts
```

## Tech Stack

- **Runtime:** Python 3.12, FastAPI, Pydantic 2.x, SQLAlchemy 2.x async
- **Database:** PostgreSQL 14+ with pgvector, Redis for caching/signals
- **AI Providers:** OpenAI, Anthropic, Groq (default), Gemini
- **Frontend:** Vanilla JS, Jinja2 templates, Lucide icons
- **Observability:** OpenTelemetry, Prometheus, structured JSON logging
- **Security:** JWT (python-jose), bcrypt, TOTP MFA, encrypted tokens
- **Deployment:** Docker, systemd, Nginx reverse proxy
