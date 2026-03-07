# AI Agent Rules for Nidin BOS

These rules apply to all AI assistants editing this repository (Claude, Copilot, Cursor, Windsurf, etc.).

---

## Before You Start

1. **Read `PROJECT_CONTEXT.md`** — understand what Nidin BOS is and how it is structured.
2. **Read `CODEBASE_MAP.md`** — understand the layer architecture before touching any file.
3. **Read `DECISIONS.md`** — understand why the architecture is the way it is.
4. **Read `CLAUDE.md`** — project-specific instructions that override defaults.
5. **Check `CURRENT_TASK.md`** — understand what is currently being worked on.

---

## Architecture Rules

### Routes Must Be Thin
- API endpoints (`app/api/v1/endpoints/`) are dispatchers only
- NO business logic in route functions
- Call service functions, record audit events, return Pydantic schemas

### All Logic in Services
- Business rules live in `app/services/`
- Services are the single source of truth
- Background jobs, web routes, API routes, and engines all call services

### Never Bypass RBAC
- Every mutating endpoint must use `require_roles()` dependency
- Never hardcode user IDs or skip authorization checks
- JWT contains `role` and `org_id` — both must be validated

### Never Bypass Approvals
- High-risk actions (sending emails, executing workflows, deleting data) require Approval records
- Do not create "shortcut" endpoints that skip the approval flow
- If an action needs approval, create an Approval then wait for human review

### Integration Pattern
- **Tool** (`app/tools/<name>.py`) — pure async httpx client, NO database
- **Service** (`app/services/<name>_service.py`) — database operations, token management
- Never mix these layers

---

## Code Standards

### Feature Flags
- New features must be gated behind `FEATURE_*` boolean in `app/core/config.py`
- Feature flag defaults to `False` (opt-in activation)
- Guard functions go in `app/application/automation/bootstrap.py` or equivalent

### Audit Events
- Every write operation must call `record_action()` from `app/logs/audit.py`
- Include: `event_type`, `actor_user_id`, `organization_id`, `entity_type`, `entity_id`

### Secrets
- All secrets come from `.env` via `app/core/config.py` Settings
- Never hardcode API keys, passwords, or tokens
- Integration tokens stored encrypted via `encrypt_config()`

### Error Handling
- Services should raise `HTTPException` or return meaningful error dicts
- Failed external calls go to dead-letter queue, not silently dropped
- Never catch and swallow exceptions without logging

### Database
- Use SQLAlchemy async sessions from `app/core/deps.get_db`
- All models inherit from `app/db/base.Base`
- Migrations via Alembic — never modify tables manually
- Foreign keys with proper cascade rules

---

## Testing Rules

### Write Tests for New Logic
- Every new service function needs at least one test
- Every new endpoint needs a happy-path test and a permission test
- Use `db` fixture for service tests, `client` fixture for API tests

### Test Patterns
- **Monkeypatch at source module:** If a function is imported inside another function, patch at the source (`app.services.xxx.fn`), not the importer
- **Feature flags:** `monkeypatch.setattr(settings, "FEATURE_XXX", True)`
- **Auth headers:** `_make_auth_headers(role="CEO", org_id=1)`
- **In-memory SQLite:** Tests use SQLite — skip pgvector operations gracefully

### Do Not Break Existing Tests
- Run `python -m pytest tests/ -x -q` before considering work done
- Current baseline: 1986+ tests passing, 3 skipped

---

## What NOT to Do

- Do not create documentation files unless explicitly asked
- Do not add comments to code you did not change
- Do not refactor code beyond what the task requires
- Do not add type annotations to unchanged code
- Do not over-engineer — solve the current problem, not hypothetical future ones
- Do not use `git push --force`, `git reset --hard`, or skip hooks
- Do not commit `.env`, credentials, or secrets
- Do not add dependencies without justification
- Do not create microservices — this is a modular monolith by design

---

## Checklist Before Submitting Changes

- [ ] Read the files I am modifying before editing
- [ ] Business logic is in services, not routes
- [ ] RBAC enforced on new endpoints
- [ ] Audit events recorded for mutations
- [ ] Feature-flagged if it is a new feature
- [ ] Tests written and passing
- [ ] Full test suite still green
- [ ] No secrets hardcoded
- [ ] No unnecessary files created
