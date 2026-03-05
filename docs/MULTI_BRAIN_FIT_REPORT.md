# Multi-Brain Architecture Fit Report

> Generated 2026-03-05 — Principal Architect review of Nidin BOS against the Multi-Workspace AI Operating System plan.

---

## 1. Current Architecture Map

### Core Flow

```
User → /web/* (cookie auth) → pages.py → templates (Jinja2)
     → /api/v1/* (Bearer auth) → router.py → 40+ endpoint modules → services → SQLAlchemy models → PostgreSQL
                                                                   → ai_router.py → Groq/OpenAI/Anthropic/Gemini
```

### Isolation Boundaries

| Layer | Isolation Unit | Workspace-Aware? |
|-------|---------------|-------------------|
| Auth (deps.py) | `org_id` from JWT | No workspace claim |
| RBAC (rbac.py) | Role-based (`CEO`, `ADMIN`, `MANAGER`, `STAFF`) | No workspace-level perms |
| Memory (memory.py) | `organization_id` + nullable `workspace_id` | **Yes** (Phase 2) |
| AI Router (ai_router.py) | `organization_id`, `BrainContext` | Partial — `BrainContext` exists but unused by callers |
| Agent Orchestrator (agents/orchestrator.py) | `organization_id` | No workspace routing |
| Approvals (approval.py) | `organization_id` | No workspace scope |
| Automation (automation.py) | `organization_id` | No workspace scope |
| Integrations (integrations.py) | `organization_id` | No workspace scope |
| Compliance (compliance_engine.py) | `organization_id` | No workspace scope |
| Tasks/Projects/Goals | `organization_id` | No workspace scope |

### Key Models (workspace-aware)

| Model | `workspace_id` | Constraint |
|-------|----------------|------------|
| `Workspace` | — (is the entity) | `UniqueConstraint(org_id, slug)` |
| `WorkspaceMembership` | FK | `UniqueConstraint(workspace_id, user_id)` |
| `ProfileMemory` | FK (nullable) | `UniqueConstraint(org_id, key, workspace_id)` |
| `AvatarMemory` | FK (nullable) | `UniqueConstraint(org_id, avatar_mode, key, workspace_id)` |
| `DailyContext` | FK (nullable) | Indexed `(org_id, date)` |
| `SharePacket` | FK (source + target) | — |
| `DecisionCard` | FK | — |

### Key Models (NOT workspace-aware)

| Model | Current Isolation |
|-------|-------------------|
| `Task` | `organization_id` only |
| `Project` | `organization_id` only |
| `Goal` | `organization_id` only |
| `Approval` | `organization_id` only |
| `AuditLog` | `organization_id` only |
| `AutomationTrigger` | `organization_id` only |
| `AutomationWorkflow` | `organization_id` only |
| `Integration` | `organization_id` only |
| `Notification` | `user_id` only |

---

## 2. Fit Verdict

### A. Workspace Isolation — Can each workspace operate as an independent AI brain?

**Verdict: FITS with minor extensions**

**Evidence:**
- `app/models/workspace.py` — `Workspace` model has `workspace_type` (general/department/project/client), `config_json` for per-workspace settings, `is_active` flag
- `app/services/workspace.py` — Full CRUD: `create_workspace`, `list_workspaces`, `get_workspace`, `update_workspace`
- `WorkspaceMembership` with `role_override` enables per-workspace permission overrides

**Gap:** No workspace-scoped `config_json` schema for AI personality, prompt templates, or behavioral settings per brain. The field exists but is unstructured.

### B. Memory — Does each brain have its own isolated memory?

**Verdict: FITS**

**Evidence:**
- `app/models/memory.py` — `ProfileMemory`, `AvatarMemory`, `DailyContext` all have nullable `workspace_id` FK
- `app/services/memory.py` — All memory functions accept `workspace_id` parameter; queries add `WHERE workspace_id = ?` when provided
- Cache key is `tuple[int, int | None]` — `(org_id, workspace_id)`
- `invalidate_memory_cache(org_id, workspace_id=None)` — NULL clears all org caches, specific ID clears one workspace
- Unique constraints include `workspace_id` — same key can exist in different workspaces
- `app/services/clone_memory.py` — `store_memory`, `retrieve_similar`, `decay_old_memories`, `get_memory_stats` all accept `workspace_id`

**Tests:** `tests/test_workspace_memory.py` — 5 tests verifying isolation, cross-workspace independence, and cache correctness.

### C. Orchestrator — Can a CEO-level view aggregate all workspace brains?

**Verdict: FITS**

**Evidence:**
- `app/services/orchestrator.py` — `generate_briefing(db, org_id)` aggregates:
  - Total/active workspaces
  - Per-workspace health scores (memory richness + decision velocity + activity + connectivity = 0-100)
  - Pending decisions and shares counts
  - Cross-workspace patterns (overlap, gap, bottleneck)
- `app/schemas/orchestrator.py` — `OrchestratorBriefing` with `workspace_health: list[WorkspaceHealth]` and `patterns: list[CrossWorkspacePattern]`
- `app/api/v1/endpoints/orchestrator.py` — `GET /orchestrator/briefing` (CEO/ADMIN), `GET /orchestrator/workspace-health/{id}` (CEO/ADMIN/MANAGER)

**Tests:** `tests/test_orchestrator.py` — 12 tests covering empty org, multi-workspace, pattern detection, health scoring, RBAC.

### D. Share Packets — Can workspaces exchange knowledge safely?

**Verdict: FITS**

**Evidence:**
- `app/models/share_packet.py` — `SharePacket` with `source_workspace_id`, `target_workspace_id`, `content_type` (memory/context/insight/task), `status` (proposed/approved/rejected/applied)
- `app/services/share_packet.py` — Full lifecycle: create → decide (approve/reject) → apply (copies memory to target workspace)
- Apply logic handles 3 content types: memory (upserts ProfileMemory), context (creates DailyContext), insight (creates ProfileMemory with category=insight)
- Self-share validation: source != target enforced at API layer

**Tests:** `tests/test_share_packets.py` — 12 tests covering CRUD, approval flow, apply with verification, RBAC.

### E. Decision Cards — Can workspace brains surface decisions for human review?

**Verdict: FITS**

**Evidence:**
- `app/models/decision_card.py` — `DecisionCard` with `workspace_id`, `options_json` (2-6 structured options), `urgency`, `category`, `source_type` (ai_agent/manual/automation/share_packet)
- `app/services/decision_card.py` — Create, decide, defer, list with filters, pending count
- `app/api/v1/endpoints/decision_cards.py` — 6 endpoints with audit trail via `record_action()`

**Tests:** `tests/test_decision_cards.py` — 13 tests covering full lifecycle.

### F. Human-in-the-Loop — Is the approval system ready for workspace-scoped actions?

**Verdict: FITS with extension needed**

**Evidence:**
- `app/services/approval.py` — Mature approval flow: `request_approval()` → pending → `approve_approval()`/`reject_approval()`
- Atomic UPDATE WHERE prevents race conditions
- SLA-based expiry from `APPROVAL_SLA_HOURS`
- Notification on approval/rejection

**Gap:** Approval model uses `organization_id` only — no `workspace_id` column. To scope approvals per workspace brain, the model needs a nullable `workspace_id` FK. This is a single-column addition + migration, not a redesign.

### G. UI Impact — Can the web layer support workspace switching?

**Verdict: NEEDS WORK**

**Evidence:**
- `app/web/pages.py` — All `_web_page()` calls pass `org_id` from session, no workspace context
- `app/templates/` — No workspace selector in sidebar or nav
- `window.__bootPromise` returns a JWT with org_id but no workspace claim
- `app/api/v1/endpoints/chat.py` — Chat endpoint uses org_id, no workspace routing

**Required changes:**
1. Add workspace selector to sidebar (`partials/sidebar.html`)
2. Store active workspace in session or cookie
3. Pass `workspace_id` through `_web_page()` to templates
4. Update `window.__bootPromise` or add `window.__activeWorkspace`
5. Chat endpoint needs `workspace_id` query param

### H. Observability — Can we monitor per-workspace health?

**Verdict: FITS**

**Evidence:**
- Orchestrator health scoring already computes per-workspace metrics
- `app/services/trend_telemetry.py` — Command center / incident snapshot (org-level, extensible to workspace)
- `app/logs/audit.py` — `record_action()` takes `entity_type` + `entity_id` — workspace actions are auditable
- Prometheus instrumentator in main.py for HTTP metrics

**Gap:** No per-workspace Prometheus labels. Workspace health is computed on-demand, not pushed to metrics. For production monitoring, add workspace_id label to key counters.

---

## 3. Gap List

| # | Gap | Severity | Files Affected | Effort |
|---|-----|----------|----------------|--------|
| G1 | AI Router lacks workspace context propagation | High | `app/services/ai_router.py`, `app/agents/orchestrator.py` | Medium — `BrainContext` exists, callers need to pass it |
| G2 | Agent orchestrator routes by org, not workspace | High | `app/agents/orchestrator.py` | Medium — add workspace_id to `run_agent()` / `run_agent_multi_turn()` |
| G3 | Chat endpoint has no workspace scope | High | `app/api/v1/endpoints/chat.py` | Small — add `workspace_id` query param, pass to agent |
| G4 | Approval model missing workspace_id | Medium | `app/models/approval.py`, `app/services/approval.py` | Small — nullable FK + migration |
| G5 | Task/Project/Goal models missing workspace_id | Medium | `app/models/task.py`, `project.py`, `goal.py` | Medium — nullable FK + service layer updates |
| G6 | Automation triggers/workflows not workspace-scoped | Medium | `app/models/automation.py`, `app/services/automation.py` | Medium — nullable FK + filter updates |
| G7 | Web layer has no workspace context | Medium | `app/web/pages.py`, templates, sidebar | Medium — session/cookie + UI |
| G8 | Integration connections are org-level only | Low | `app/models/integration.py` | Low priority — most integrations are org-wide |
| G9 | No per-workspace Prometheus metrics | Low | `app/main.py` | Small — add label to instrumentator |
| G10 | `config_json` on Workspace has no schema | Low | `app/models/workspace.py` | Small — add Pydantic schema for brain config |

---

## 4. Risk List

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| R1 | Breaking existing API consumers | High | All workspace_id params are nullable — NULL = org-level (backward compatible) |
| R2 | Memory cache explosion with many workspaces | Medium | `_prune_memory_cache()` already enforces MAX_CACHE_SIZE=50; monitor hit rate |
| R3 | Cross-workspace data leakage | High | All queries use `organization_id` as outer fence; workspace_id narrows within org |
| R4 | Orchestrator N+1 queries | Medium | `generate_briefing()` queries per-workspace in loop; batch with `selectinload` for >20 workspaces |
| R5 | Share packet apply without validation | Medium | `apply_share_packet()` copies memory directly; add content validation/sanitization |
| R6 | Decision card expiry not enforced | Low | `expires_at` exists but no background job checks it; add to scheduler |

---

## 5. Minimal Redesign Proposal (Backwards Compatible)

### Phase 6 — AI Brain Isolation (Priority: High)

**Goal:** Make each workspace's AI conversations use workspace-scoped memory and context.

1. **`app/agents/orchestrator.py`** — Add `workspace_id` param to `run_agent()` and `run_agent_multi_turn()`. Pass to `build_memory_context(org_id, workspace_id=workspace_id)`. Pass to `call_ai()` via `BrainContext`.

2. **`app/services/ai_router.py`** — `BrainContext` already exists. Ensure `_prepend_brain_context()` includes workspace name/type in system prompt. No model changes needed.

3. **`app/api/v1/endpoints/chat.py`** — Add `workspace_id: int | None = Query(None)` param. Pass through to agent orchestrator.

### Phase 7 — Workspace-Scoped Entities (Priority: Medium)

Add nullable `workspace_id` FK to:
- `Task`, `Project`, `Goal` — with service layer filter updates
- `Approval` — scope approval flows to workspace context
- `AutomationTrigger`, `AutomationWorkflow` — workspace-specific automations

Pattern (same as memory):
```python
workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
```

### Phase 8 — Web Layer Workspace Context (Priority: Medium)

1. Add `active_workspace_id` to web session (cookie or DB-backed)
2. Add workspace selector dropdown to `partials/sidebar.html`
3. Update `_web_page()` to pass `workspace_id` to all template contexts
4. Update `window.__bootPromise` response to include `active_workspace_id`
5. Dashboard JS reads workspace from boot and filters API calls

### Phase 9 — Observability & Polish (Priority: Low)

1. Add `workspace_id` label to Prometheus HTTP metrics
2. Background job to expire stale DecisionCards (`expires_at < now()`)
3. Add `BrainConfig` Pydantic schema for `Workspace.config_json`
4. Dashboard widget for orchestrator briefing (CEO view)

---

## 6. Test Plan

| Phase | Test File | What to Verify |
|-------|-----------|----------------|
| 6 | `tests/test_brain_isolation.py` | Chat in workspace A doesn't see workspace B memory; BrainContext propagated to AI calls |
| 7 | `tests/test_workspace_tasks.py` | Task CRUD scoped to workspace; NULL workspace returns all org tasks |
| 7 | `tests/test_workspace_approvals.py` | Approval created with workspace_id; list filters by workspace |
| 8 | `tests/test_web_workspace.py` | Workspace selector sets session; pages render workspace context |
| 9 | `tests/test_decision_expiry.py` | Scheduler marks expired cards; orchestrator excludes them |

### Existing Tests (must stay green)

```
python -m pytest tests/ -x -q
# Current: 1601 passed, 3 skipped
```

All new workspace_id params are nullable — existing tests pass without modification.

---

## 7. Summary

| Area | Status | Notes |
|------|--------|-------|
| Workspace model | Done | Full CRUD, types, membership, config_json |
| Memory isolation | Done | All 3 memory models workspace-aware, cache updated |
| Share packets | Done | Full lifecycle with apply logic |
| Decision cards | Done | Human-in-the-loop with audit trail |
| CEO orchestrator | Done | Health scoring, pattern detection, briefing |
| AI brain isolation | **Gap** | BrainContext exists but not wired through agent layer |
| Entity scoping | **Gap** | Tasks, projects, goals, approvals need workspace_id |
| Web layer | **Gap** | No workspace selector or context switching |
| Observability | Partial | On-demand health works; no push metrics |

**Bottom line:** The multi-brain foundation is solid. Phases 1-5 delivered the hardest parts — workspace model, memory isolation, cross-workspace communication, and orchestration. The remaining gaps (G1-G10) are incremental additions following the same nullable-FK pattern already proven in the memory layer. No architectural redesign needed.
