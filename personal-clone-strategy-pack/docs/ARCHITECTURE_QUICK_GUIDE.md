# Architecture Quick Guide

## Auth Flow
- API login: `POST /token` returns bearer JWT.
- Web login: `POST /web/login` sets `pc_session` and `pc_csrf` cookies.
- Role and org scope are encoded in JWT claims (`id`, `role`, `org_id`).
- RBAC checks run in endpoint dependencies (`require_roles(...)`).

## Ingestion Flow
- Integration credentials are stored in `Integration.config_json` (encrypted at rest path in token crypto layer).
- Ingestion services read from providers:
  - ClickUp tasks
  - GitHub PR/issues
  - Gmail metadata
- Payloads are sanitized and saved into `IntegrationSignal`.
- Weekly metrics derive from `IntegrationSignal` and upsert into ops metric tables.

## Privacy Model
- `app/core/privacy.py` applies key-based redaction plus text masking.
- Profiles:
  - `strict`: always mask PII (including IP in free text).
  - `balanced`: follow `PRIVACY_MASK_PII`.
  - `debug`: keep PII visible, always redact secrets.
- Response sanitization protects legacy rows before returning API payloads.
- Audit log sanitizer runs before DB writes.
