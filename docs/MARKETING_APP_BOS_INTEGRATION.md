# Marketing / Campaigns App — BOS Integration

BOS decides **who we contact, how often, and with what**. The Marketing (or campaigns) app must call BOS before any send; it must not implement contact policy or rate limits on its own.

---

## Authentication

BOS API key or service user JWT for the marketing org. Base URL: `BOS_BASE_URL`.

---

## Endpoint to call

### Can send (before every send)

**When:** Before sending any outbound message (email, SMS, etc.) to a contact.

**Call:** `POST /api/v1/control/levers/can-send`

**Body:**
```json
{
  "organization_id": 1,
  "contact_id": "contact-uuid-123",
  "channel": "email",
  "campaign_id": "campaign-456"
}
```

**Response:** `{ "allowed": true, "reason": null, "recommended_time_utc": "2025-03-12T10:00:00Z" }`  
(Current stub: always allowed with current time. Later BOS will enforce rate limits and policy.)

**What the app must do:**
- If `allowed` is false, do **not** send; show `reason` to the user.
- If allowed, prefer `recommended_time_utc` for scheduling when possible.
- Do not send without calling this endpoint first.
- **After each send,** call `POST /api/v1/control/levers/record-send` with `organization_id`, `contact_id`, `channel` so BOS can enforce per-contact daily limits.

---

## Record send (after each send)

**Call:** `POST /api/v1/control/levers/record-send`  
**Body:** `{ "organization_id": 1, "contact_id": "...", "channel": "email" }`  
**Response:** 204 No Content.

**Contact ID:** Use your BOS contact ID (string), or a stable external id (e.g. normalized recipient email) so rate limits apply per recipient.

### External ESPs (SendGrid, Mailchimp, etc.)

If sends go through an external ESP, either:

1. **From your app:** After your app triggers a send (e.g. via ESP API), call `record-send` with the same `organization_id`, `contact_id` (recipient id or email), and `channel` (e.g. `"email"`).
2. **Webhook from ESP:** If the ESP sends a "delivered" or "sent" webhook to your backend, have that handler call BOS `POST /api/v1/control/levers/record-send` with the recipient mapped to `contact_id`. Use the same auth (API key or JWT) as other BOS calls.

---

## Summary

- **BOS owns:** Contact policy and “can we send to this contact on this channel now?”
- **Marketing app:** Calls BOS before every send and obeys the response; no own policy or rate-limit logic.
