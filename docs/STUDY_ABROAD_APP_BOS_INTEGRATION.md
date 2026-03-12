# Study Abroad App (ESA) — BOS Integration

BOS is the control plane for **application milestones** and **risk status**. The Study Abroad app must call BOS for these; it must not implement timeline or risk logic on its own.

---

## Authentication

Same as other control integrations: BOS API key or service user JWT, with `organization_id` for the study-abroad org. Base URL: `BOS_BASE_URL` (e.g. `https://bos.youcompany.com`).

---

## Endpoints to call

### 1. Next required steps

**When:** After any change to an application (e.g. document uploaded, step completed).

**Call:** `POST /api/v1/control/levers/study-abroad/application-milestones`

**Body:**
```json
{
  "organization_id": 1,
  "application_id": "app-uuid-123"
}
```

**Response (stub):** `{ "application_id": "...", "steps": [], "deadline": null }`  
Later BOS will return real steps and deadline from milestone config.

**What the app must do:** Use `steps` and `deadline` to drive the applicant UI and reminders. Do not compute “next steps” locally.

---

### 2. Risk status

**When:** When displaying application health or dashboard.

**Call:** `POST /api/v1/control/levers/study-abroad/risk-status`

**Body:**
```json
{
  "organization_id": 1,
  "application_id": "app-uuid-123"
}
```

**Response (stub):** `{ "application_id": "...", "status": "on_track", "message": null, "critical_deadlines": [] }`  
Later BOS will return real status (e.g. at_risk, critical) and deadlines.

**What the app must do:** Show BOS status and escalate based on `critical_deadlines`. Do not compute risk locally.

---

## Summary

- **BOS owns:** What the next steps are and whether an application is on track / at risk.
- **Study Abroad app:** Calls BOS, displays the result, and collects input; no own milestone or risk logic.
