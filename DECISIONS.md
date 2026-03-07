# Architectural Decisions

## ADR-001: Modular Monolith over Microservices

**Decision:** Build as a single FastAPI application with clear module boundaries instead of separate microservices.

**Rationale:**
- Single developer/small team — operational simplicity is critical
- Shared database with strong foreign keys ensures data integrity
- Module boundaries enforced by convention (services never import from API layer)
- Can extract modules into services later if scaling demands it

**Consequences:** All code deploys together. Module boundaries must be enforced by code review and convention.

---

## ADR-002: Service Layer for All Business Logic

**Decision:** API routes are thin dispatchers. All business logic lives in `app/services/`.

**Rationale:**
- Testable without HTTP — call service functions directly with a DB session
- Reusable — web routes, API routes, background jobs, and engines all call the same services
- Single source of truth for business rules

**Pattern:**
```python
# Endpoint (thin)
@router.post("/tasks")
async def create_task(data: TaskCreate, db=Depends(get_db), actor=Depends(require_roles("CEO"))):
    task = await task_service.create_task(db, organization_id=actor["org_id"], data=data)
    await record_action(db, event_type="task_created", ...)
    return TaskRead.model_validate(task)
```

---

## ADR-003: Human-in-the-Loop Approval System

**Decision:** All high-risk AI actions require explicit human approval before execution.

**Rationale:**
- AI autonomy must be bounded — mistakes can send real emails, modify real data
- Approval creates an auditable decision point
- CEO/ADMIN can review context before committing

**Flow:** Action proposed → Approval created → Human reviews → Approved/Rejected → Execution (if approved) → Audit recorded.

---

## ADR-004: Role-Based Access Control (RBAC)

**Decision:** Use role-based access with `require_roles()` FastAPI dependency on every endpoint.

**Roles:** CEO > ADMIN > MANAGER > STAFF

**Rationale:**
- Simple and predictable access model
- Single-org, small-team use case doesn't need attribute-based access
- Enforced at the route level — impossible to bypass

**Implementation:** `app/core/rbac.py` — JWT contains `role`, `org_id`. Dependency validates both.

---

## ADR-005: Signals and Event-Driven Observability

**Decision:** Use an internal signal/event system (`app/platform/signals/`) for cross-cutting concerns.

**Rationale:**
- Decouples audit logging, notification dispatch, and analytics from core business logic
- Services emit signals; consumers handle side effects independently
- Enables future async processing without changing service code

**Components:**
- `publisher.py` — Emit signals with topic, payload
- `consumers.py` — Register handlers per topic
- `store.py` — Persist signals for replay/audit

---

## ADR-006: Feature Flags for Progressive Rollout

**Decision:** Gate new features behind `FEATURE_*` boolean settings in `app/core/config.py`.

**Rationale:**
- Deploy code without activating features
- Enable per-environment (dev vs prod) feature control
- Clean rollback — disable flag, feature disappears

**Examples:** `FEATURE_WORKFLOW_V2`, `FEATURE_WORKFLOW_RUNS`, `FEATURE_WORKFLOW_COPILOT`, `FEATURE_WORKFLOW_EXEC_INSIGHTS`

---

## ADR-007: Integration Pattern (Tools + Services)

**Decision:** Every external integration follows a strict two-layer pattern.

| Layer | Location | Rules |
|-------|----------|-------|
| Tool | `app/tools/<name>.py` | Pure async httpx client. NO database. NO state. Just HTTP calls. |
| Service | `app/services/<name>_service.py` | Database operations, token management, sync logic, caching. |

**Rationale:**
- Tools are testable in isolation (mock HTTP, not DB)
- Services handle the messy state (token refresh, sync status, error recording)
- Clear separation prevents accidental coupling

---

## ADR-008: Encrypted Integration Tokens

**Decision:** All third-party API tokens stored encrypted in the database using Fernet symmetric encryption.

**Implementation:** `app/core/token_crypto.py` — `encrypt_config()` / `decrypt_config()` on integration `config_json`.

**Rationale:** Defense in depth. Even if DB is compromised, tokens are useless without the encryption key (from `.env`).

---

## ADR-009: Audit Trail Immutability

**Decision:** Audit events are append-only. No updates or deletes on audit log records.

**Implementation:** `app/logs/audit.py` — `record_action()` inserts an event with actor, entity, payload, timestamp.

**Rationale:** Compliance and forensics. Must be able to reconstruct exactly what happened and who did it.

---

## ADR-010: AI Provider Abstraction

**Decision:** Route AI calls through `app/services/ai_router.py` which dispatches to the configured provider.

**Providers:** OpenAI (default for email), Groq (default for fast responses), Anthropic, Gemini.

**Rationale:**
- Swap providers without changing calling code
- Per-use-case provider selection (email drafting uses OpenAI, quick classification uses Groq)
- Fallback chains possible

---

## ADR-011: Dead-Letter Queue for Failed Operations

**Decision:** Failed side effects (email sends, webhook deliveries, integration syncs) go to a dead-letter queue instead of being silently dropped.

**Implementation:** `app/platform/dead_letter/` — `store.py` captures failures, `inspector.py` allows review, `reprocessor.py` enables retry.

**Rationale:** No operation should be silently lost. Failed actions can be inspected and retried.

---

## ADR-012: pgvector for Semantic Memory

**Decision:** Use PostgreSQL pgvector extension for embedding-based memory retrieval instead of external vector databases.

**Rationale:**
- Single database — no additional infrastructure
- Cosine similarity search via `<=>` operator with HNSW index
- Falls back gracefully to lexical search when embeddings unavailable
