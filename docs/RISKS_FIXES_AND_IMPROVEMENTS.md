# Project audit: risks, fixes, and improvements

Summary of a full-project review for Nidin BOS (architecture, tenant isolation, RBAC, lint, and docs).

---

## What was fixed in this pass

### 1. **CLAUDE.md — Known issues**
- **Before:** Listed three “current known issues” (optional `organization_id` in `list_tasks`/`list_goals`, and layers_pkg org filters).
- **After:** Confirmed all three are already correct: `list_tasks` and `list_goals` require `organization_id`; `people.py`, `clone.py`, and `marketing.py` use `Task.organization_id == organization_id` and `Contact.organization_id == organization_id` in all relevant selects. Section updated to “(None at this time)” and points to `tests/test_architecture_guards.py`.

### 2. **Lint (ruff)**
- **Import order:** Sorted/fixed in `app/api/v1/endpoints/leads.py`, `app/api/v1/router.py`, `app/platform/signals/__init__.py` (and any others auto-fixed).
- **`__all__`:** Sorted in `app/platform/signals/__init__.py`.
- **social_ingest.py:** Removed unused `Contact` import; used `contextlib.suppress(ValueError, TypeError)` for the SLA datetime parse (SIM105).
- **tests/conftest.py:** E402 “import not at top” after the Python 3.14/SQLAlchemy compat block is intentional; added `# noqa: E402` on those imports so ruff passes without changing test setup.

### 3. **Architecture guards**
- Re-ran `tests/test_architecture_guards.py`: all 5 tests pass (brain no DB mutation, tenant awareness, where filter, mutating routes protected, sensitive routes gated).

---

## Verified (no change needed)

- **Tenant isolation:** `list_tasks`, `list_goals` take required `organization_id`. Layers_pkg `select(Task)` and `select(Contact)` all include `.where(…organization_id == organization_id)`.
- **Brain engine:** No `db.add`, `db.commit`, or `db.delete` in `app/engines/brain/`.
- **RBAC:** Sampled POST/PUT/PATCH/DELETE endpoints use `require_roles()` or equivalent (e.g. `get_current_api_user` for leads with org check). Leads ingest is restricted to Empire Digital org.
- **Protected fields:** `TaskUpdate`, `ContactUpdate`, and goal update schemas do not expose `id`, `organization_id`, `created_at`, or `created_by_user_id`.
- **Optional `organization_id` in services:** Grep found only legitimate optional args (e.g. `workspace_id`, `created_by`, `parent_organization_id`). No service list/query function makes `organization_id` optional.

---

## Remaining ruff (optional / style)

- **E712** (e.g. `== True` / `== False`) in several services: `department.py`, `email_sequence.py`, `employee.py`, `governance.py`, `knowledge_base.py`, `learning_feedback.py`, `media_storage.py`, `meeting_scheduler.py`, `metrics_service.py`, `performance.py`, `policy_service.py`, `report_service.py`. These are style suggestions (e.g. `if x:` vs `if x is True:`). Can be fixed in a dedicated style pass if you want zero ruff errors.
- **conftest E402:** Suppressed with noqa; leaving the compat block before app imports is correct.

---

## Risks and recommendations

### Low risk (already guarded or documented)
- **Cross-org access:** Only allowed for CEO + Empire Digital per `app/core/lead_routing.py`; leads ingest enforces `EMPIRE_DIGITAL_COMPANY_ID` in the API.
- **Mutating routes:** Architecture test ensures POST/PUT/PATCH/DELETE under `/api/v1/` return 401/403 without auth (public paths allowlisted).
- **Control/levers:** Sensitive control routes are allowlisted in `TestSensitiveRoutesGated`.

### Good to keep an eye on
- **New services:** Any new service that uses `select()` and `db.execute()` must include `organization_id` in the file and use `.where()` for tenant filtering; `test_services_with_select_mention_organization_id` and `test_services_with_select_use_where_filter` will catch most mistakes. Allowlist in `test_architecture_guards.py` is minimal (`embedding.py`, `lead_routing_policy.py`, `api_key.py`).
- **New mutating endpoints:** Always use `require_roles()` (or equivalent) and pass `organization_id` from the actor; run the architecture guards after adding routes.
- **Update schemas:** When adding new *Update schemas, do not include `id`, `organization_id`, `created_at`, or `created_by_user_id` (CLAUDE.md protected-fields rule).

### Optional future improvements (from PENDING_IMPROVEMENTS.md)
- Staging gate: fail deploy if new money/communications flows skip approvals.
- Control levers: real `can_send` policy and rate limits, richer `route_lead` rules, study-abroad milestones, money approval matrix by role/amount.
- Recruitment: richer routing rules and SLA config per org.

---

## How to re-run checks

```bash
python -m pytest tests/test_architecture_guards.py -v
python -m ruff check app tests
python scripts/dev_gate.py   # full quality gate
```

Running the full test suite (`pytest tests/ -q`) is recommended before commits; architecture guards are a fast subset for quick validation.
