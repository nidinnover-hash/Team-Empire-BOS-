# CLAUDE.md — Nidin BOS Development Instructions

## Project Identity
You are working on **Nidin BOS** — a production-grade AI-powered Business
Operating System built by Nidin Nover for Team Empire.

Repo: nidinnover-hash/Team-Empire-BOS-
Stack: Python 3.12, FastAPI, SQLAlchemy (async), Alembic, PostgreSQL,
Jinja2, Vanilla JS

Companies powered by BOS:
- EmpireO.ai — International recruitment (MEA)
- ESA (Empire Study Abroad) — Study abroad services
- Empire Digital — Marketing, sales, lead generation
- Codnov.ai — AI product development

---

## Architecture — Non-Negotiable Rules

### Layer Order (never bypass)
Data Layer → Service Layer → API Layer → AI Layer → Execution Layer

### 1. Tenant Isolation
- EVERY query MUST filter by `organization_id`
- NEVER make `organization_id` optional in service functions
- Pattern: `select(Model).where(Model.organization_id == organization_id)`
- No cross-org data access unless role is CEO + org is EMPIRE_DIGITAL_COMPANY_ID

### 2. Service Layer
- API endpoints NEVER query the database directly
- All business logic lives in `app/services/`
- Services receive `organization_id` as a required parameter

### 3. RBAC — Always Enforce
Use `require_roles()` from `app/core/rbac.py` on every endpoint.
Role hierarchy: CEO > ADMIN > MANAGER > STAFF
```python
# Example
actor: dict = Depends(require_roles("CEO", "ADMIN"))
actor: dict = Depends(require_sensitive_financial_roles())
actor: dict = Depends(require_ceo_executive_roles())
```

### 4. AI Must Never Mutate the Database
- Brain engine only returns `ProposedAction` objects
- All AI-triggered actions go through `approval_service` → `execution_service`
- Never add `db.add()` or `db.commit()` inside `app/engines/brain/`

### 5. Audit Trail — Every Write
Every mutation must emit a signal or log an event:
```python
from app.platform.signals import publisher, topics
await publisher.publish(SignalEnvelope(
    topic=topics.CONTACT_CREATED,
    organization_id=org_id,
    actor_user_id=actor["id"],
    entity_type="contact",
    entity_id=str(entity.id),
    payload_json={...},
))
```

### 6. Protected Fields
These fields must NEVER be modified via update endpoints:
`id`, `organization_id`, `created_by_user_id`, `created_at`

---

## Development Workflow

### When adding a new feature:
1. Define the SQLAlchemy model in `app/models/`
2. Generate migration: `alembic revision --autogenerate -m "add_feature"`
3. Write the service in `app/services/`
4. Add the FastAPI endpoint in `app/api/v1/endpoints/`
5. Write tests in `tests/` covering:
   - Happy path
   - Tenant isolation (org A cannot access org B data)
   - RBAC (wrong role gets 403)
   - Idempotency if applicable

### Model pattern:
```python
class MyModel(Base):
    __tablename__ = "my_table"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
```

### Service pattern:
```python
async def create_thing(
    db: AsyncSession,
    data: ThingCreate,
    organization_id: int,   # always required, never Optional
    actor_user_id: int,
) -> Thing:
    thing = Thing(**data.model_dump(), organization_id=organization_id)
    db.add(thing)
    await db.commit()
    await db.refresh(thing)
    return thing
```

### Endpoint pattern:
```python
@router.post("/", response_model=ThingRead, status_code=201)
async def create_thing(
    data: ThingCreate,
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    org_id = int(actor["org_id"])
    return await thing_service.create_thing(db, data, organization_id=org_id, actor_user_id=actor["id"])
```

---

## Key Files to Know

| File | Purpose |
|------|---------|
| `app/main.py` | App entry, middleware, startup guards |
| `app/core/deps.py` | Auth, session, workspace resolution |
| `app/core/rbac.py` | `require_roles()`, role guards |
| `app/core/config.py` | All settings via pydantic-settings |
| `app/platform/signals/` | Signal publish/subscribe system |
| `app/platform/signals/topics.py` | All official signal topic strings |
| `app/engines/brain/` | AI reasoning (no DB mutations here) |
| `app/engines/execution/` | Workflow execution runtime |
| `app/services/approval.py` | Approval gate before execution |
| `app/core/audit_integrity.py` | HMAC chain audit signing |
| `app/core/lead_routing.py` | Cross-company contact visibility |

---

## Testing Rules

Run before every commit:
```bash
pytest tests/ -q                    # all 1849+ tests must pass
ruff check app tests                # zero lint errors
python scripts/dev_gate.py         # full quality gate
```

Every new feature needs:
- Unit test for the service function
- Integration test with real DB (use `db` fixture from `conftest.py`)
- Isolation test: create two orgs, verify org A cannot read org B's data
- RBAC test: verify STAFF gets 403 on CEO-only endpoints

---

## Current Known Issues to Fix

- *(None at this time.)* All list/get services require `organization_id` for tenant isolation.
  Run `tests/test_architecture_guards.py` to enforce tenant awareness and layers_pkg org filters.

---

## Signal Topics Quick Reference
```python
from app.platform.signals import topics

topics.CONTACT_CREATED        # contact.created
topics.EXECUTION_COMPLETED    # execution.completed
topics.WORKFLOW_RUN_COMPLETED # workflow.run.completed
topics.APPROVAL_REQUESTED     # approval.requested
topics.USER_LOGIN             # user.login
topics.AI_CALL_COMPLETED      # ai.call.completed
```

---

## Never Do These

- Never add `organization_id: int | None = None` in service functions
- Never call `db.execute(select(Model))` without an org filter
- Never add DB mutations inside `app/engines/brain/`
- Never skip `require_roles()` on a write endpoint
- Never hardcode API keys or secrets — use `app/core/config.py` settings
- Never delete audit events — the `before_delete` listener will raise
- Never change `id`, `organization_id`, or `created_at` in update endpoints

---

## Companies & Org IDs

Empire Digital has a special org ID constant used for cross-company
lead routing. Find it in `app/core/lead_routing.py` as
`EMPIRE_DIGITAL_COMPANY_ID`. Do not hardcode this value elsewhere.
