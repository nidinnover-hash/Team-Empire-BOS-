# Pending improvements — status and next steps

Quick reference for what was done and what remains from the BOS improvement plan.

---

## Done (this round)

### Architecture guards
- **`tests/test_architecture_guards.py`**
  - **Brain no DB mutation:** Fails CI if `db.add(`, `db.commit(`, or `db.delete(` appear in `app/engines/brain/`.
  - **Tenant awareness:** Services with `select(` and `execute(` must reference `organization_id` (allowlist for cross-org modules).
  - **Mutating routes protected:** Fails if any POST/PUT/PATCH/DELETE under `/api/v1/` returns 200 without `Authorization` (public webhooks/auth excluded).
- **`scripts/dev_gate.py`** runs these tests as part of the developer gate.

### Audit helper
- **`app/core/audit_helpers.py`** — `record_critical_mutation()` for critical writes. Used in recruitment `confirm-placement` and `request-money-approval`.

### Recruitment control (EmpireO)
- **`POST /api/v1/control/recruitment/route-candidate`** — assign owner and SLA for new candidates.
- **`POST /api/v1/control/recruitment/assign-owner`** — allow or deny ownership change.
- **`POST /api/v1/control/recruitment/candidate-stage`** — allow/deny stage change; require approval for “offer”.
- **`POST /api/v1/control/recruitment/confirm-placement`** — record placement for audit (+ audit event).
- **`POST /api/v1/approvals/request`** with `approval_type: "recruitment_offer"` — risky approval for offers.

### Control levers (BOS as single control plane)
- **`POST /api/v1/control/levers/can-send`** — contact policy (real: `ContactSendPolicy` + `ContactSendLog`, rate limits).
- **`POST /api/v1/control/levers/record-send`** — record send for rate-limit counting.
- **`POST /api/v1/control/levers/route-lead`** — lead routing; returns owner and SLA (uses `RecruitmentRoutingRule` + org policy).
- **`POST /api/v1/control/levers/request-money-approval`** — creates money approval; auto-approve via `MoneyApprovalMatrix` by role/amount.
- **`POST /api/v1/control/levers/study-abroad/application-milestones`** — real steps from `StudyAbroadApplicationStep` + templates.
- **`POST /api/v1/control/levers/study-abroad/risk-status`** — real status from pending deadlines (on_track / at_risk / critical).

### Control report by org
- **Control Dashboard** — “Control report (by org)” card shows event counts by organization (last 7 days: placement_confirmed, money_approval_requested). **`GET /api/v1/control/observability/control-report`** returns by_event_type and by_organization (with org slug).

### Staging gate extension (done)
- **`TestMoneyAndCommunicationsFlowsGated`** — fails deploy if new POST routes for money/communications are added outside the allowlist (control levers, approvals, webhooks, etc.). See `tests/test_architecture_guards.py`.

Docs: `docs/RECRUITMENT_APP_BOS_INTEGRATION.md`, `docs/RECRUITMENT_APP_GO_LIVE.md`.

---

## Still pending (optional)

### Architecture / quality
- *(None.)* Staging gate extended; tenant guards and layers_pkg audit in place.

### Control levers (further enhancements)
- **route_lead:** Even richer rules (e.g. more product_line/region combos) and SLA config per org — already supported by `RecruitmentRoutingRule` and org policy.

### Done (optional round — items 3–4)
- **Tenant guard tightened:** Services with select+execute+org must also use `.where(` (allowlist: api_key.py).
- **Layers_pkg tenant audit:** `TestLayersPkgTenantAudit` — every `select(Task)`/`select(Contact)` in layers_pkg must include organization_id in `.where(`.
- **Recruitment placements:** `recruitment_placements` table (migration 20260312_0089); `confirm_placement` persists and emits `RECRUITMENT_PLACEMENT_CONFIRMED`.
- **Staging gate:** `TestSensitiveRoutesGated` — control/levers mutating routes must be allowlisted; `TestMoneyAndCommunicationsFlowsGated` — money/comm routes must be allowlisted.
- **Integration docs:** Study Abroad, Marketing, Billing — `docs/STUDY_ABROAD_APP_BOS_INTEGRATION.md`, `docs/MARKETING_APP_BOS_INTEGRATION.md`, `docs/BILLING_MONEY_APP_BOS_INTEGRATION.md`.

### Recruitment (optional)
- Richer routing rules (by region/product_line) and SLA config per org — already supported; optional UI/config for managing rules.

---

## How to run the new guards

```bash
python -m pytest tests/test_architecture_guards.py -v
# or
python scripts/dev_gate.py
```
