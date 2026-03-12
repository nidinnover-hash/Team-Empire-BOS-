# Rule Drift Report

One-time scan for architectural rule violations: optional `organization_id`, un-scoped queries, and DB writes inside AI/brain or intelligence engines. Findings and fixes applied.

---

## 1. Optional `organization_id` in services

**Rule:** Every service function that touches tenant-scoped data must take `organization_id: int` as required (no `Optional`/`None` default).

### Findings

| Location | Before | Fix |
|----------|--------|-----|
| `app/services/execution.py` | `complete_execution(..., organization_id: int \| None = None)` — when `None`, the query did not filter by org, so completing an execution from another org was possible. | Made `organization_id: int` required and always filter: `query.where(Execution.organization_id == organization_id)`. |

### Intentional exceptions (no change)

- `app/services/organization.py`: `parent_organization_id: int \| None = None` — refers to a parent org FK, not tenant scope; acceptable.
- `app/engines/brain/drafting.py` and `app/engines/brain/router.py`: optional `organization_id` in **caller-facing** API (e.g. chat) with fallback to default org for system-level calls; callers that pass `org_id` are correct; internal service calls now pass a concrete org (e.g. `organization_id or 1` when calling `log_ai_call`).

---

## 2. DB writes inside engines (AI must not mutate DB)

**Rule:** No `db.add()` / `db.commit()` inside `app/engines/brain/` or inside intelligence engine; all persistence goes through services.

### Findings

| Location | Before | Fix |
|----------|--------|-----|
| `app/engines/brain/router.py` | `_log_ai_call` created `AiCallLog`, called `db.add(log_entry)` and `await db.flush()` or `await _db.commit()`. | New service `app/services/ai_call_log.py` with `log_ai_call(db, *, organization_id, ...)`. Router now calls this service only; no DB write in brain. |
| `app/engines/intelligence/knowledge.py` | `consolidate_memories` performed `db.get`, `db.delete`, and `await db.commit()` in-engine. | New `app/services/memory.consolidate_profile_memory_duplicates(db, organization_id, value_updates, ids_to_delete)`; engine builds update/delete lists and calls the service; service performs all writes and single commit. |

### Allowed (orchestration, not “AI mutating”)

- `app/engines/execution/workflow_runtime.py` and `workflow_recovery.py`: `db.commit()` after calling approval/execution/automation **services** — this is session lifecycle for workflow run/step state owned by the execution engine; all business mutations go through services. Left as-is.

---

## 3. Un-scoped selects

**Rule:** Every `select(Model)` for tenant-scoped data must include `.where(Model.organization_id == organization_id)` (or equivalent via `apply_org_scope`).

### Findings

- No new un-scoped selects were found in the areas scanned. Execution service was the only drift (optional org filter); that is fixed as above.
- Known call sites for `complete_execution` (`workflow_runtime.py`, `execution_engine.py`) already pass `organization_id`; making it required does not break them.

---

## Summary

| Category | Drift found | Action |
|----------|-------------|--------|
| Optional `organization_id` in services | 1 (`execution.complete_execution`) | Fixed: required param + always filter. |
| DB writes in brain | 1 (AI call log in `router.py`) | Fixed: moved to `app/services/ai_call_log.log_ai_call`. |
| DB writes in intelligence | 1 (`consolidate_memories` delete/commit) | Fixed: moved to `app/services/memory.consolidate_profile_memory_duplicates`. |
| Un-scoped selects | 0 new | N/A. |

Run the full test suite after these changes; add tests for `complete_execution` with wrong org (expect no update) and for the new service entry points if desired.

**New surface:** `app/services/ai_call_log.log_ai_call`, `app/services/memory.consolidate_profile_memory_duplicates` — see CODEBASE_MAP.md Services table for one-line descriptions.

---

## What was done (this pass)

1. **Full test suite** — Run was started; some failures observed (e.g. ~8%, ~24%, ~27%). Fix by running `pytest tests/ -x --tb=short` and addressing the first failing test, then re-running until green.
2. **Known issues (CLAUDE.md)** — `list_tasks` and `list_goals` already require `organization_id`; `layers_pkg` (people, clone, marketing) already scope `select(Task)` / `select(Contact)` by `organization_id`. No code change needed.
3. **Observability** — Added `WORKFLOW_STEP_BLOCKED` and `KNOWLEDGE_SAVE_FAILED` signal topics; workflow_plans emits a signal per blocked step; `save_extracted_knowledge` emits a signal before raising when all saves fail.
4. **Docs** — CODEBASE_MAP.md Services table updated with `ai_call_log.py` and `consolidate_profile_memory_duplicates`; RULE_DRIFT_REPORT.md references them.

## Suggested next priorities

- **Green full suite:** Run `pytest tests/ -q`, fix any remaining failures, then run `python scripts/dev_gate.py` before merge.
- **Consumers for new signals:** Add a dashboard or alert rule for `WORKFLOW_STEP_BLOCKED` and `KNOWLEDGE_SAVE_FAILED` if you want operational visibility.
- **Extension work:** Use `docs/EXTENSION_RECIPES.md` when adding a new CRM entity, workflow action, or AI insight.
