# Billing / Money App — BOS Integration

**No money action without a BOS approval.** Refunds, payouts, credits, discounts, or any financial action must be requested through BOS; the app must not execute until BOS returns an approved approval.

---

## Authentication

BOS API key or service user JWT for the org. Base URL: `BOS_BASE_URL`.

---

## Endpoint to call

### Request money approval (before any money action)

**When:** Before executing any money-affecting action (refund, payout, credit, discount, etc.).

**Call:** `POST /api/v1/control/levers/request-money-approval`

**Body:**
```json
{
  "organization_id": 1,
  "action_type": "refund",
  "amount": 150.00,
  "currency": "USD",
  "payload": {
    "order_id": "ord-123",
    "reason": "customer_return"
  }
}
```

**Response:** `{ "approval_id": 901, "status": "pending" }` (or `"approved"` if auto-approved).

**What the app must do:**
1. Store `approval_id` on the money-action record.
2. Do **not** execute the action (e.g. do not call payment gateway) until the approval `status` is `approved`. Poll `GET /api/v1/approvals/{approval_id}` or use BOS webhooks.
3. If `status` is `rejected`, do not execute; show rejection to the user.
4. After executing, you can report back via your own API or future BOS endpoint.

---

## Summary

- **BOS owns:** Whether a money action is allowed (approval matrix by role/amount later).
- **Billing/Money app:** Calls BOS for every money action, waits for approval, then executes; no execution without BOS approval_id.
