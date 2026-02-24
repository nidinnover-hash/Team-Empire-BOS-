# Customization Guide

This guide shows exactly what to edit for common customization goals.

## 1) Change Business Rules Fast

- Edit env values in `.env.empireo`.
- Core settings live in `app/core/config.py`.

Common examples:

- Compliance owner/team emails:
  - `COMPLIANCE_OWNER_EMAILS`
  - `COMPLIANCE_TECH_LEAD_EMAIL`
  - `COMPLIANCE_OPS_MANAGER_EMAIL`
  - `COMPLIANCE_DEV_EMAILS`
- Company domain and exceptions:
  - `COMPLIANCE_COMPANY_DOMAIN`
  - `COMPLIANCE_ALLOWED_PERSONAL_EMAILS`
- Privacy/security profile:
  - `PRIVACY_POLICY_PROFILE`
  - `SECURITY_PREMIUM_MODE`
  - `ACCOUNT_MFA_REQUIRED`

## 2) Customize Control API Behavior

- CEO/control endpoints:
  - `app/api/v1/endpoints/control.py`
- Integrations behavior:
  - `app/api/v1/endpoints/integrations.py`
  - `app/api/v1/endpoints/integrations_github.py`
  - `app/api/v1/endpoints/integrations_clickup.py`
  - `app/api/v1/endpoints/integrations_digitalocean.py`
  - `app/api/v1/endpoints/integrations_slack.py`

Use this when you want to change response format, add new control routes, or modify summary logic.

## 3) Customize Layer Scoring and Insights

- Main logic:
  - `app/services/layers.py`
- Response schemas:
  - `app/schemas/layers.py`
- Layer routes:
  - `app/api/v1/endpoints/layers.py`

You can tune score weights, bottleneck conditions, risk thresholds, and next-action wording here.

## 4) Customize Compliance Engine

- Policy logic:
  - `app/services/compliance_engine.py`
- Compliance endpoints:
  - `app/api/v1/endpoints/control.py`

Use this for:

- New policy checks
- Severity changes
- Custom ownership/permission rules
- Industry-specific governance checks

## 5) Customize Clone Brain Training

- Clone training/scoring:
  - `app/services/clone_brain.py`
- Clone control mappings/profiles:
  - `app/services/clone_control.py`
- Ops training endpoints:
  - `app/api/v1/endpoints/ops.py`

Use this to tune:

- Readiness levels
- Dispatch logic
- Feedback adjustment impact
- Weekly training flow

## 6) Customize UI and Dashboard

- HTML templates:
  - `app/templates/dashboard.html`
  - `app/templates/integrations.html`
  - `app/templates/data_hub.html`
- Frontend JS:
  - `app/static/js/dashboard-page.js`
  - `app/static/js/integrations-page.js`
- Styles:
  - `app/static/css/dashboard.css`
  - `app/static/css/theme.css`

## 7) Add New Data Fields Safely

1. Update model in `app/models/...`.
2. Add Alembic migration in `alembic/versions/...`.
3. Update Pydantic schema in `app/schemas/...`.
4. Update service logic in `app/services/...`.
5. Update endpoint in `app/api/v1/endpoints/...`.
6. Add/adjust tests in `tests/...`.

## 8) Most Common Customization Tasks

- Add a new integration:
  - Add endpoint file under `app/api/v1/endpoints/`
  - Add service in `app/services/`
  - Add schema in `app/schemas/integration.py`
  - Include router in `app/api/v1/endpoints/integrations.py`
- Add a new layer:
  - Add schema in `app/schemas/layers.py`
  - Add computation in `app/services/layers.py`
  - Expose route in `app/api/v1/endpoints/layers.py`
- Add a new control summary:
  - Add schema in `app/schemas/control.py`
  - Add endpoint in `app/api/v1/endpoints/control.py`

## 9) Quality Checklist After Any Customization

Run:

- `.\.venv\Scripts\ruff.exe check app tests`
- `.\.venv\Scripts\python.exe -m mypy app tests`
- `.\.venv\Scripts\python.exe -m pytest -q`

If full `pytest` is slow, run targeted tests first (for changed modules), then full suite.

## 10) Recommended Safe Pattern

- Keep all irreversible/execution actions approval-gated.
- Keep suggest-only behavior for control/compliance by default.
- Keep secrets in env, never hardcoded.
- Keep org isolation checks on every query path.
