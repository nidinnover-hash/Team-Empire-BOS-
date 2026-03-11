# Extension Recipes

Step-by-step patterns for adding a new CRM entity, a new workflow action type, and a new AI-powered insight. Follow the layer order: **Data → Service → API → (Engines)** and enforce tenant isolation, RBAC, and audit on every write.

---

## 1. Adding a new CRM entity

Example: adding something like "Quotes" (see `app/models/quote.py`, `app/services/quote.py`, `app/api/v1/endpoints/quotes.py`).

### 1.1 Model

- **Where:** `app/models/<entity>.py`
- **Pattern:**
  - `id`, `organization_id` (FK to `organizations.id`, `nullable=False`, `index=True`), `created_at` / `updated_at` as needed.
  - No optional `organization_id`.
- **Reference:** `app/models/quote.py`, `CLAUDE.md` model pattern.

### 1.2 Migration

- `alembic revision --autogenerate -m "add_<entity>_table"`
- Review the generated migration; ensure `organization_id` has an index and correct FK.

### 1.3 Service

- **Where:** `app/services/<entity>.py`
- **Pattern:**
  - All functions take `organization_id: int` (required).
  - Use `apply_org_scope(select(...), Model, organization_id)` for every query.
  - Protect `id`, `organization_id`, `created_by_user_id`, `created_at` on updates (`_PROTECTED_FIELDS`).
  - No business logic in the API layer; all CRUD and rules here.
- **Reference:** `app/services/quote.py`.

### 1.4 Feature flag and bootstrap

- **Config:** Add `FEATURE_<ENTITY>` (default `False`) in `app/core/config.py` if the entity is gated.
- **Bootstrap:** In `app/application/crm/bootstrap.py` (or equivalent), add `async def <entity>_enabled(db, organization_id) -> bool` that checks the feature flag / per-org override (e.g. `feature_flags.is_effective_feature_enabled(..., flag_name="<entity>", ...)`).
- **Reference:** `quotes_enabled`, `playbooks_enabled` in `app/application/crm/bootstrap.py`.

### 1.5 API endpoint

- **Where:** `app/api/v1/endpoints/<entity>.py`
- **Pattern:**
  - Router with prefix and tags.
  - Every mutating route: `Depends(require_roles(...))`, then call service with `actor["org_id"]` and `actor["id"]`.
  - After each write, call `record_action(db, event_type="<entity>_created"|..., actor_user_id=actor["id"], organization_id=actor["org_id"], entity_type="<entity>", entity_id=..., payload_json=...)`.
  - For gated entities: at the start of each handler, `await _require_<entity>(db, actor["org_id"])`; if disabled, raise `HTTPException(404, "Not found")`.
- **Router registration:** Include the router in `app/api/v1/router.py` (e.g. `api_router.include_router(<entity>.router, prefix="/<entity>", tags=[...])`).
- **Reference:** `app/api/v1/endpoints/quotes.py`.

### 1.6 Tests

- Happy path: create/list/get/update/delete with valid `organization_id` and role.
- Tenant isolation: create in org A, assert org B cannot read/update/delete.
- RBAC: assert lower role (e.g. STAFF) gets 403 where required.
- Feature flag: with flag off, expect 404 on the gated endpoints.

---

## 2. Adding a new workflow action type

Workflow steps are executed by the execution engine; each step has an `action_type` and `params`. You add a handler and wire it into the plan and policy.

### 2.1 Handler implementation

- **Where:** `app/services/execution_engine.py`
- **Pattern:**
  - Define a function `_handler_<action>(payload: dict[str, Any]) -> dict[str, Any]` (or async). It receives the step’s `params`; return a dict (e.g. `{"action": "<action>", ...}`).
  - Add it to the `HANDLERS` dict: `"<action_type>": _handler_<action>`.
- **Reference:** `_handler_send_email`, `_handler_create_task`, `HANDLERS` in `app/services/execution_engine.py`.

### 2.2 Planner and policy

- **Brain planner:** In `app/engines/brain/workflow_planner.py`, add the new action type to `KNOWN_ACTION_TYPES` so the AI can propose it. Adjust the system prompt / heuristic if you have special rules (e.g. “mark as requires_approval”).
- **Decision policy:** In `app/engines/decision/workflow_policy.py`:
  - If the action is read-only/safe, add it to `SAFE_AUTO_ACTIONS` or keep the `fetch_`/`read_` prefix convention so it can auto-approve.
  - If it is mutating or sensitive, do **not** add to `SAFE_AUTO_ACTIONS`; it will default to `REQUIRES_APPROVAL`.
  - If it must never run, add a prefix to `BLOCKED_ACTION_PREFIXES`.

### 2.3 Execution flow

- The execution engine gets `action_type` and `params` from the workflow step/plan, calls `dispatch_workflow_step_handler(action_type, params)` (which uses `HANDLERS` from `execution_engine`), then completes the execution and updates the run. No need to touch `workflow_runtime.py` unless you change orchestration behavior.

### 2.4 Tests

- Add a test that runs a workflow with a step using the new `action_type` and asserts the handler is invoked and the execution completes (and, if applicable, that approval is required when policy says so).

---

## 3. Adding a new AI-powered insight

“Insight” here means logic that uses the AI (brain/router) or intelligence engine to produce recommendations, summaries, or structured data. Rule: **AI engines do not mutate the DB**; they call services for any persistence.

### 3.1 Where the logic lives

- **Brain** (`app/engines/brain/`): workflow planning, copilot suggestions, one-off AI calls. Use `app/engines/brain/router.call_ai` for LLM calls; do not add `db.add()` / `db.commit()` here.
- **Intelligence** (`app/engines/intelligence/`): knowledge extraction, memory consolidation, knowledge graph, rankings. Read from DB only via services or org-scoped queries; writes go through services (e.g. `memory.upsert_profile_memory`, `memory.consolidate_profile_memory_duplicates`).

### 3.2 Pattern for a new insight

1. **Inputs:** Get `organization_id` (and optionally `workspace_id`) from the caller; never make tenant scope optional in the engine’s public API when it touches data.
2. **Read data:** Use service functions (e.g. `get_profile_memory`, `list_*`) or, if you must query in-engine, use `select(Model).where(Model.organization_id == organization_id)` (and optional workspace filter). Do not run un-scoped selects.
3. **Call AI:** Use `call_ai` (or equivalent) from the brain router; pass the chosen provider/model and prompt. Parse the response in-engine; do not persist inside the router.
4. **Write data:** For any new or updated entities, call a service (e.g. in `app/services/memory.py`, or a dedicated insight service). The service performs `db.add` / `db.commit` and, where appropriate, emits audit/signals.
5. **Return:** Return structured data (dicts, Pydantic models) to the caller; the API or job that invoked the engine can then call more services or return HTTP responses.

### 3.3 Example: “Save extracted knowledge”

- **Engine:** `app/engines/intelligence/knowledge.py` — `extract_knowledge_from_conversation` (AI or heuristic) produces `KnowledgeEntry` objects; `save_extracted_knowledge` calls `app.services.memory.upsert_profile_memory` for each entry with `organization_id` and optional `workspace_id`. No direct DB write in the engine.
- **Consolidation:** `consolidate_memories` builds update/delete lists and calls `app.services.memory.consolidate_profile_memory_duplicates`; the service does all DB writes and commit.

### 3.4 Tests

- Unit test the engine function with mocked services; assert it calls the right service methods with the right `organization_id` and does not call `db.commit` or `db.add` in the engine.
- Integration test: call the API or job that uses the insight, then assert persisted data via services and that tenant isolation holds (e.g. org B has no access to org A’s insight data).

---

## Quick reference

| Goal              | Key files |
|-------------------|-----------|
| New CRM entity    | `app/models/`, `app/services/`, `app/api/v1/endpoints/`, `app/application/crm/bootstrap.py`, `app/core/config.py`, `app/api/v1/router.py` |
| New workflow action | `app/services/execution_engine.py` (HANDLERS), `app/engines/brain/workflow_planner.py` (KNOWN_ACTION_TYPES), `app/engines/decision/workflow_policy.py` |
| New AI insight    | `app/engines/brain/` or `app/engines/intelligence/`, plus `app/services/` for all persistence; never `db.add`/`db.commit` in engines |
