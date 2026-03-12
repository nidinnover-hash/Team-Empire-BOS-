# Control plane — apps integration checklist

All apps that touch **contacts**, **leads**, **money**, **recruitment**, or **study abroad** must go through BOS. Use this checklist and the per-app docs.

---

## One pattern

1. **Before** a controlled action (send, route, offer, money, milestone), call the **BOS control endpoint**.
2. **Obey** the response (allowed/owner/approval_id).
3. **After** the action when BOS needs to know (e.g. after send for rate limits), call the **BOS record endpoint** if documented.

---

## By app

| App | Before action | After action | Doc |
|-----|----------------|--------------|-----|
| **Recruitment** | route-candidate, candidate-stage, approvals/request (offer) | confirm-placement | [RECRUITMENT_APP_BOS_INTEGRATION.md](RECRUITMENT_APP_BOS_INTEGRATION.md), [RECRUITMENT_APP_GO_LIVE.md](RECRUITMENT_APP_GO_LIVE.md) |
| **Study Abroad (ESA)** | — | — | [STUDY_ABROAD_APP_BOS_INTEGRATION.md](STUDY_ABROAD_APP_BOS_INTEGRATION.md) — call **application-milestones** and **risk-status** for timeline and risk. |
| **Marketing / Campaigns** | can-send | record-send | [MARKETING_APP_BOS_INTEGRATION.md](MARKETING_APP_BOS_INTEGRATION.md) |
| **Billing / Money** | request-money-approval | — | [BILLING_MONEY_APP_BOS_INTEGRATION.md](BILLING_MONEY_APP_BOS_INTEGRATION.md) — wait for approval before executing. |

---

## BOS base URL and auth

- **Base URL:** from env (e.g. `BOS_BASE_URL`).
- **Auth:** API key or JWT with correct `organization_id`. Create keys in BOS (CEO/ADMIN): `POST /api/v1/api-keys`.

---

## Control dashboard and report

- **Dashboard:** `GET /api/v1/control/dashboard/control-summary` — pending approvals, recent placements, money approvals, study-abroad at-risk count.
- **Observability report:** `GET /api/v1/control/observability/control-report` — event counts by type and org (last 7 days).
