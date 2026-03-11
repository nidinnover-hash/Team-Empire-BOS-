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
- **`POST /api/v1/control/levers/can-send`** — contact policy (stub: allowed + now).
- **`POST /api/v1/control/levers/route-lead`** — lead routing; returns owner and SLA.
- **`POST /api/v1/control/levers/request-money-approval`** — creates money approval, returns approval_id (+ audit).
- **`POST /api/v1/control/levers/study-abroad/application-milestones`** — stub: empty steps.
- **`POST /api/v1/control/levers/study-abroad/risk-status`** — stub: on_track.

Docs: `docs/RECRUITMENT_APP_BOS_INTEGRATION.md`, `docs/RECRUITMENT_APP_GO_LIVE.md`.

---

## Still pending (optional)

### Architecture / quality
- **Staging gate extension:** Fail deploy if new money/communications flows skip approvals (beyond current guards).

### Control levers (enhancements)
- **can_send:** Real contact policy and rate limits (DB/config).
- **route_lead:** Richer rules by region/lead_type and SLA config.
- **Study abroad:** Application/milestone model and real deadlines.
- **Money approvals:** Approval matrix by role/amount (config).

### Recruitment (optional)
- Persist placement records in BOS (e.g. `recruitment_placements` table) and optionally emit signals for analytics.
- Richer routing rules (by region/product_line) and SLA config per org.

---

## How to run the new guards

```bash
python -m pytest tests/test_architecture_guards.py -v
# or
python scripts/dev_gate.py
```
