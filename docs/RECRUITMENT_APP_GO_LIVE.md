# Recruitment App — Go-Live Checklist (Option 1)

Get the existing Recruitment App live on BOS with **two integration points**: route new candidates and approve offers. No rebuild — just add BOS API calls and remove in-app routing/approval logic.

---

## Part A — For you (BOS admin)

### 1. Create a BOS API key for the Recruitment App

1. Log in to BOS as **CEO or ADMIN** for the **recruitment organization** (EmpireO).
2. Call the API key creation endpoint (or use the BOS UI if it has one):
   - **POST** `https://<BOS_BASE_URL>/api/v1/api-keys`
   - **Headers:** `Authorization: Bearer <your_jwt>` (from your BOS login).
   - **Body:**
     ```json
     {
       "name": "Recruitment App",
       "scopes": "read,write",
       "expires_in_days": 365
     }
     ```
3. **Save the returned `key`** (shown only once). Share it securely with the team (e.g. env var `BOS_API_KEY`). Do not commit it to the Recruitment App repo.

### 2. Share with the team

- **BOS base URL:** e.g. `https://bos.youcompany.com` (no trailing slash).
- **API key:** the value from step 1 (store in env, not in code).
- **Docs:**  
  - `docs/RECRUITMENT_APP_BOS_INTEGRATION.md` — full contract.  
  - This file — go-live steps.

### 3. Confirm BOS is ready

- [ ] `POST /api/v1/control/recruitment/route-candidate` is deployed and returns `owner_user_id` / `sla_first_contact_at`.
- [ ] `POST /api/v1/approvals/request` accepts `approval_type: "recruitment_offer"` and appears in BOS approvals list.
- [ ] At least one active user in the recruitment org has a role that can own candidates (e.g. STAFF, MANAGER).

---

## Part B — For the team (Recruitment App codebase)

Use **one** BOS base URL and **one** API key (env vars). Example:

- `BOS_BASE_URL` = `https://bos.youcompany.com`
- `BOS_API_KEY` = `<secret from Part A>`

All requests: **Headers:** `Authorization: Bearer <BOS_API_KEY>` and `Content-Type: application/json`.

---

### Integration 1 — New candidate: get owner and SLA from BOS

**When:** Right after the Recruitment App creates a new candidate (or imports a lead) in your database.

**Do:**

1. Call BOS **POST** `{BOS_BASE_URL}/api/v1/control/recruitment/route-candidate` with body:

   ```json
   {
     "organization_id": <your_org_id>,
     "candidate_id": "<your_candidate_id_or_uuid>",
     "job_id": "<job_id_or_null>",
     "source": "<linkedin|website|import|...>",
     "region": "<MEA|...>",
     "product_line": "<tech|...>"
   }
   ```

2. From the response:
   - If **`allowed` is false:** do not assign the candidate to the pipeline (or put in a queue); show **`reason`** to the user.
   - If **`allowed` is true:** store **`owner_user_id`** (and optionally **`owner_email`**) as the **primary owner** of this candidate. Store **`sla_first_contact_at`** and use it for “Contact by” deadline and reminders.

**Example (pseudo-code):**

```python
async def after_candidate_created(candidate_id: str, job_id: str | None, source: str, ...):
    resp = await http.post(
        f"{settings.BOS_BASE_URL}/api/v1/control/recruitment/route-candidate",
        json={
            "organization_id": settings.BOS_ORG_ID,
            "candidate_id": candidate_id,
            "job_id": job_id,
            "source": source,
            "region": getattr(candidate, "region", None),
            "product_line": getattr(candidate, "product_line", None),
        },
        headers={"Authorization": f"Bearer {settings.BOS_API_KEY}"},
    )
    data = resp.json()
    if not data.get("allowed"):
        # Show data["reason"] to user; do not assign
        return
    # Save to your DB:
    # candidate.owner_user_id = data["owner_user_id"]
    # candidate.owner_email = data["owner_email"]
    # candidate.sla_first_contact_at = data["sla_first_contact_at"]
```

**Remove:** Any logic in the Recruitment App that **decides** who owns a new candidate (e.g. round-robin, region-based assignment). That now comes only from BOS.

---

### Integration 2 — Offer: get BOS approval before creating/sending

**When:** Before the Recruitment App **creates** or **sends** an offer to a candidate (e.g. when the recruiter clicks “Send offer” or “Create offer”).

**Do:**

1. Call BOS **POST** `{BOS_BASE_URL}/api/v1/approvals/request` with:
   - **Header:** `Idempotency-Key: offer-<candidate_id>-<job_id>-<timestamp_or_unique_id>` (so duplicate clicks don’t create two approvals).
   - **Body:**
     ```json
     {
       "organization_id": <your_org_id>,
       "approval_type": "recruitment_offer",
       "payload_json": {
         "candidate_id": "<candidate_id>",
         "job_id": "<job_id>",
         "salary_amount": 120000,
         "currency": "AED",
         "start_date": "2025-04-01",
         "role_title": "Senior Engineer",
         "source_system": "recruitment_app"
       }
     }
     ```

2. Store **`approval.id`** on the offer record in your app.

3. **Do not send the offer** until the approval **`status`** is **`approved`**:
   - **Option A — Poll:** Periodically call **GET** `{BOS_BASE_URL}/api/v1/approvals?status=pending` (or GET `.../approvals/{approval.id}`) until that approval’s `status` is `approved` or `rejected`.
   - **Option B — Webhooks:** If BOS is configured to send `approval.approved` / `approval.rejected` webhooks to your app, use those to unblock the “send offer” flow.

4. If **`status` is `rejected`:** do not send the offer; show the rejection to the recruiter.

5. If **`status` is `approved`:** proceed to create/send the offer in your app (and optionally notify BOS later when you add `confirm-placement`).

**Example (pseudo-code):**

```python
async def before_send_offer(candidate_id: str, job_id: str, salary: int, currency: str, start_date: str, role_title: str):
    idempotency_key = f"offer-{candidate_id}-{job_id}-{int(time.time())}"
    resp = await http.post(
        f"{settings.BOS_BASE_URL}/api/v1/approvals/request",
        headers={
            "Authorization": f"Bearer {settings.BOS_API_KEY}",
            "Idempotency-Key": idempotency_key,
        },
        json={
            "organization_id": settings.BOS_ORG_ID,
            "approval_type": "recruitment_offer",
            "payload_json": {
                "candidate_id": candidate_id,
                "job_id": job_id,
                "salary_amount": salary,
                "currency": currency,
                "start_date": start_date,
                "role_title": role_title,
                "source_system": "recruitment_app",
            },
        },
    )
    approval = resp.json()
    # Store approval["id"] on the offer record
    if approval["status"] == "approved":
        return "ok"  # Proceed to send offer
    if approval["status"] == "rejected":
        return "rejected"
    # status == "pending" -> poll GET /api/v1/approvals/{approval["id"]} until approved/rejected
    while True:
        poll = await http.get(
            f"{settings.BOS_BASE_URL}/api/v1/approvals/{approval['id']}",
            headers={"Authorization": f"Bearer {settings.BOS_API_KEY}"},
        )
        a = poll.json()
        if a["status"] == "approved":
            return "ok"
        if a["status"] == "rejected":
            return "rejected"
        await asyncio.sleep(5)
```

**Remove:** Any logic that **approves** offers inside the Recruitment App (e.g. “manager approval” or “auto-approve”). Offer approval is only via BOS.

---

### Checklist for the team

- [ ] Env vars set: `BOS_BASE_URL`, `BOS_API_KEY`, `BOS_ORG_ID` (recruitment org id in BOS).
- [ ] On **new candidate:** call `POST .../control/recruitment/route-candidate` and save owner + SLA; remove in-app routing logic.
- [ ] On **offer:** call `POST .../approvals/request` with `recruitment_offer`, wait for `approved`, then send; remove in-app offer-approval logic.
- [ ] Test: create a candidate → verify owner is set from BOS; create an offer → verify it stays pending until approved in BOS, then sends.

---

## After go-live

- You control **who** gets each candidate and **whether** each offer is allowed from BOS.
- Later you can add: `assign-owner`, `candidate-stage`, and `confirm-placement` so all ownership and placement changes go through BOS too (see `RECRUITMENT_APP_BOS_INTEGRATION.md`).
