# OAuth Recovery (Gmail)

Use this when Gmail OAuth appears connected but `/api/v1/email/sync` fails.

## Symptoms
- `POST /api/v1/email/sync` returns `502`
- Error code/detail shows one of:
  - `gmail_reconnect_required`
  - `gmail_api_disabled`
  - `gmail_upstream_error`
- Callback works but sync still fails.

## Quick Checks
1. Confirm API is running:
`GET /health`
2. Confirm Gmail integration status:
`GET /api/v1/email/health`
3. If health code is `gmail_api_disabled`, enable Gmail API:
`https://console.developers.google.com/apis/api/gmail.googleapis.com/overview`

## Full Recovery Steps
1. Remove app access in Google Account Security (third-party app access).
2. Ensure OAuth client redirect URI is exactly:
`http://127.0.0.1:8001/api/v1/email/callback`
3. Delete stale Gmail integration row from local DB (if needed).
4. Restart API server.
5. Generate fresh auth URL:
`GET /api/v1/email/auth-url`
6. Open only the latest auth URL (do not reuse old callback tabs/URLs).
7. Complete consent, verify callback returns:
`{"status":"connected","message":"Gmail connected successfully"}`
8. Immediately run:
`POST /api/v1/email/sync`
9. Verify inbox:
`GET /api/v1/email/inbox?unread_only=false&limit=20`

## Common Failure Causes
- `Invalid OAuth state`: stale URL tab or delayed callback.
- `deleted_client`: OAuth client was removed in Google Cloud.
- `accessNotConfigured`: Gmail API not enabled for the project.
- `invalid_grant`: revoked/expired refresh token, requires re-consent.

## Notes
- Keep one active OAuth flow at a time.
- Always use a fresh `auth_url` generated right before opening.
- If API keys/secrets were exposed in logs/chat, rotate them.
