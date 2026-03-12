# Recruitment App — BOS Integration Spec

This document defines **exactly when and how the Recruitment App (EmpireO) must call BOS** so that you control pipeline, ownership, and offers from one place. The Recruitment App must not implement routing, offer approval, or placement logic itself; it calls BOS.

---

## Combining existing apps with BOS (no rebuild needed)

Your team has already built the Recruitment App. **You do not need to rebuild it.** You combine it with BOS by adding BOS API calls at specific points:

1. **Keep the existing app** — same UI, same database, same flows.
2. **Insert BOS calls** at the right moments:
   - When a **new candidate** is created → call BOS `POST /api/v1/control/recruitment/route-candidate`, then store the returned `owner_user_id` and `sla_first_contact_at` in your app.
   - When an **offer** is about to be created or sent → call BOS `POST /api/v1/approvals/request` with `approval_type: "recruitment_offer"`, wait for `approved`, then proceed.
3. **Remove or disable** only the logic that *decides* ownership and *approves* offers inside the Recruitment App; that logic now lives in BOS.

Result: BOS controls **who** gets the candidate and **whether** the offer is allowed; the Recruitment App still does the rest (CRUD, UI, emails, etc.). No full rewrite — just integration points.

---

## 1. Authentication

The Recruitment App calls BOS using **one of**:

- **Option A (recommended): BOS API key**  
  - Create an API key in BOS for the recruitment org, with scopes that allow: `approvals:write`, and any scope used by the control endpoints below.  
  - Send it in the `Authorization` header: `Bearer <api_key>` or as configured in BOS.  
  - BOS will set `actor["org_id"]` from the key; the Recruitment App must use the same org for all requests.

- **Option B: Service user (JWT)**  
  - A dedicated BOS user (e.g. "Recruitment App") with role MANAGER (or as required by BOS RBAC).  
  - Recruitment App stores the user’s JWT and sends it in `Authorization: Bearer <token>`.

**Base URL:** `BOS_URL` (e.g. `https://bos.youcompany.com`). All paths below are relative to `/api/v1`.

---

## 2. When to Call BOS — Summary

| # | Recruitment App event | BOS endpoint to call | When |
|---|------------------------|----------------------|------|
| 1 | New candidate created or lead received | `POST /control/recruitment/route-candidate` | As soon as the candidate is created or imported. |
| 2 | Candidate stage change | `POST /control/recruitment/candidate-stage` | Before updating stage in the Recruitment App. |
| 3 | Offer created / sent | `POST /approvals/request` (then poll or webhook) | Before creating or sending any offer. |
| 4 | Placement confirmed | `POST /control/recruitment/confirm-placement` | After placement is confirmed (BOS records and audit). |
| 5 | Ownership change (reassign recruiter) | `POST /control/recruitment/assign-owner` | Before changing owner in the Recruitment App. |

If BOS does not yet expose the **control** endpoints (2, 4, 5), treat them as the **contract**: BOS will implement them; the Recruitment App should call them once available. Until then, the Recruitment App can use **approvals** (3) and any existing **routing** you add first.

---

## 3. Endpoint 1 — Route candidate (new candidate / lead)

**When:** The Recruitment App creates a new candidate or receives a new lead.

**Purpose:** BOS returns who owns the candidate and SLA so the Recruitment App never assigns ownership itself.

**Endpoint:** `POST /api/v1/control/recruitment/route-candidate`

**Request body:**

```json
{
  "organization_id": 1,
  "candidate_id": "rec-app-uuid-123",
  "job_id": "job-456",
  "source": "linkedin",
  "region": "MEA",
  "product_line": "tech"
}
```

**Response (200):**

```json
{
  "owner_user_id": 42,
  "owner_email": "recruiter@empireo.ai",
  "queue_id": null,
  "sla_first_contact_at": "2025-03-13T18:00:00Z",
  "allowed": true,
  "reason": null
}
```

**What the Recruitment App must do:**

- Store `owner_user_id` (and optionally `owner_email`) as the **primary owner** of this candidate for this job.
- If `allowed` is `false`, do not create the candidate in the pipeline until BOS allows it (e.g. after capacity or rule change); show `reason` to the user.
- Optionally use `sla_first_contact_at` to show a “Contact by” deadline in the UI and trigger reminders.

**If this endpoint is not yet in BOS:**  
BOS can add it later. Meanwhile, the Recruitment App can create the candidate and leave owner empty or use a default queue; as soon as `route-candidate` exists, the Recruitment App must switch to calling it and using its response for owner and SLA.

---

## 4. Endpoint 2 — Candidate stage change

**When:** User (or automation) wants to move a candidate to a new stage (e.g. Screened → Interviewing, or Interviewing → Offer).

**Purpose:** BOS can enforce rules (e.g. “offer only after interview completed”) and return whether the transition is allowed and whether an approval is required.

**Endpoint:** `POST /api/v1/control/recruitment/candidate-stage`

**Request body:**

```json
{
  "organization_id": 1,
  "candidate_id": "rec-app-uuid-123",
  "job_id": "job-456",
  "from_stage": "interviewing",
  "to_stage": "offer",
  "payload": {
    "interview_completed_at": "2025-03-12T14:00:00Z",
    "notes": "Final round done"
  }
}
```

**Response (200):**

```json
{
  "allowed": true,
  "requires_approval": true,
  "approval_type": "recruitment_offer",
  "message": "Offer stage requires approval. Create an approval request before moving."
}
```

**What the Recruitment App must do:**

- If `allowed` is `false`: do **not** change the stage; show `message` to the user.
- If `allowed` is `true` and `requires_approval` is `true`: do **not** move to `to_stage` until the Recruitment App has called BOS to create an approval (see Endpoint 3) and received approval. Then move the stage and, if applicable, create the offer.
- If `allowed` is `true` and `requires_approval` is `false`: update the stage in the Recruitment App and optionally notify BOS (e.g. for analytics).

**If this endpoint is not yet in BOS:**  
The Recruitment App can perform stage changes locally but must still use BOS for **offer** creation (Endpoint 3). When `candidate-stage` is added, switch to calling it before every stage change.

---

## 5. Endpoint 3 — Offer creation (approval)

**When:** Recruiter creates or sends an offer (salary, role, start date, etc.).

**Purpose:** No offer is valid or sent without a BOS approval record. You control who can approve and audit trail.

**Endpoint:** `POST /api/v1/approvals/request`

**Headers:**

- `Authorization: Bearer <BOS_API_KEY_OR_JWT>`
- `Idempotency-Key: <unique-key-per-offer>` (e.g. `offer-{candidate_id}-{job_id}-{timestamp}`)

**Request body (BOS standard approval request):**

```json
{
  "organization_id": 1,
  "approval_type": "recruitment_offer",
  "payload_json": {
    "candidate_id": "rec-app-uuid-123",
    "job_id": "job-456",
    "salary_amount": 120000,
    "currency": "AED",
    "start_date": "2025-04-01",
    "role_title": "Senior Engineer",
    "source_system": "recruitment_app"
  }
}
```

**Response (201):**

```json
{
  "id": 901,
  "organization_id": 1,
  "requested_by": 5,
  "approval_type": "recruitment_offer",
  "payload_json": { ... },
  "status": "pending",
  "approved_by": null,
  "approved_at": null,
  "created_at": "2025-03-12T10:00:00Z"
}
```

**What the Recruitment App must do:**

1. Before creating or sending any offer, call `POST /approvals/request` with `approval_type: "recruitment_offer"` and the offer details in `payload_json`.
2. Store `approval.id` (e.g. 901) on the offer record in the Recruitment App.
3. Do **not** send the offer to the candidate until the approval `status` is `approved`.  
   - Poll: `GET /api/v1/approvals?status=pending` (or `GET /api/v1/approvals/{id}`) until `status` is `approved` or `rejected`.  
   - Or use BOS webhooks for `approval.approved` / `approval.rejected` if configured.
4. If `status` is `rejected`, do not send the offer; show the rejection to the recruiter.
5. If `status` is `approved`, send the offer (email, contract, etc.) and optionally call BOS to report result (e.g. Endpoint 4 or a separate “offer_sent” event).

**Note:** BOS already has `POST /api/v1/approvals/request` and `GET /api/v1/approvals`. The Recruitment App uses these with `approval_type: "recruitment_offer"`. Add `recruitment_offer` to BOS approval types (and to risky-approval list if you want CEO/ADMIN approval).

---

## 6. Endpoint 4 — Confirm placement

**When:** Candidate has accepted and placement is confirmed (signed, start date set).

**Purpose:** BOS records the placement for audit and analytics; you control the single source of truth.

**Endpoint:** `POST /api/v1/control/recruitment/confirm-placement`

**Request body:**

```json
{
  "organization_id": 1,
  "candidate_id": "rec-app-uuid-123",
  "job_id": "job-456",
  "approval_id": 901,
  "placed_at": "2025-03-12T15:00:00Z",
  "start_date": "2025-04-01",
  "payload": {
    "salary_final": 120000,
    "currency": "AED"
  }
}
```

**Response (200):**

```json
{
  "recorded": true,
  "placement_id": "bos-placement-789"
}
```

**What the Recruitment App must do:**

- After confirming placement, call this endpoint so BOS can record it and maintain audit trail.
- If BOS returns an error, log it and retry; do not consider placement “synced to BOS” until 200.

**If this endpoint is not yet in BOS:**  
BOS can add it later. Until then, the Recruitment App can still record placement locally; when the endpoint exists, start calling it for every placement.

---

## 7. Endpoint 5 — Assign owner (reassign recruiter)

**When:** A manager or user reassigns the primary owner of a candidate/job.

**Purpose:** All ownership changes go through BOS so you enforce rules and audit.

**Endpoint:** `POST /api/v1/control/recruitment/assign-owner`

**Request body:**

```json
{
  "organization_id": 1,
  "candidate_id": "rec-app-uuid-123",
  "job_id": "job-456",
  "new_owner_user_id": 99,
  "reason": "rebalance"
}
```

**Response (200):**

```json
{
  "allowed": true,
  "previous_owner_user_id": 42,
  "new_owner_user_id": 99,
  "message": null
}
```

**What the Recruitment App must do:**

- Before changing the owner in the Recruitment App, call this endpoint.
- If `allowed` is `false`, do not reassign; show `message` to the user.
- If `allowed` is `true`, update the primary owner in the Recruitment App to `new_owner_user_id`.

**If this endpoint is not yet in BOS:**  
When BOS adds it, the Recruitment App must stop allowing owner changes without calling BOS (or allow only from BOS UI/sync).

---

## 8. Summary — Recruitment App checklist

- [ ] **Auth:** Recruitment App has a BOS API key (or JWT) with correct `organization_id` and scopes.
- [ ] **New candidate:** Call `POST /control/recruitment/route-candidate` and set owner and SLA from the response.
- [ ] **Stage change:** Call `POST /control/recruitment/candidate-stage` before moving stage; if `requires_approval`, create approval first (Endpoint 3).
- [ ] **Offer:** Always call `POST /approvals/request` with `approval_type: "recruitment_offer"` and wait for `approved` before sending the offer.
- [ ] **Placement:** Call `POST /control/recruitment/confirm-placement` when placement is confirmed.
- [ ] **Reassign:** Call `POST /control/recruitment/assign-owner` before changing owner in the app.

---

## 9. BOS-side work (to fully support this)

| Item | Status / action |
|------|------------------|
| `POST /approvals/request` with `recruitment_offer` | Done. Exists; `recruitment_offer` is a risky approval type. |
| `POST /control/recruitment/route-candidate` | **Done.** Returns owner and 24h SLA. |
| `POST /control/recruitment/assign-owner` | **Done.** Allows or denies ownership change. |
| `POST /control/recruitment/candidate-stage` | **Done.** Returns allowed + requires_approval (e.g. for offer). |
| `POST /control/recruitment/confirm-placement` | **Done.** Records placement and returns placement_id. |

All five recruitment control surfaces are implemented in BOS. The Recruitment App only calls BOS and obeys the responses.
