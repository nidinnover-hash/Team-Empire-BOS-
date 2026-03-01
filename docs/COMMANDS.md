# Commands

## Run app
`uvicorn app.main:app --reload`

## OAuth recovery runbook
`docs/OAUTH_RECOVERY.md`

## Run tests
`pytest -q`

## Production-like local smoke
`$env:ENFORCE_STARTUP_VALIDATION='true'; $env:COOKIE_SECURE='true'; .\.venv\Scripts\python.exe -c "from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); print('/health', c.get('/health').status_code); print('/api/v1/health', c.get('/api/v1/health').status_code)"`

## DB migration (target flow)
`alembic revision --autogenerate -m "message"`
`alembic upgrade head`

## Smoke auth flow
1. `POST /token` with form `username=demo`, `password=demo`
2. Use bearer token for `/api/v1/*`

## Full smoke test (Postman)
Base URL: `http://127.0.0.1:8000`

1. Login and get token
- Method: `POST`
- URL: `/token`
- Body type: `x-www-form-urlencoded`
- Fields:
  - `username`: your demo email (or username)
  - `password`: your demo password
- Save `access_token` from response.

2. Add profile memory
- Method: `POST`
- URL: `/api/v1/memory/profile`
- Headers:
  - `Authorization: Bearer <access_token>`
  - `Content-Type: application/json`
- Body:
```json
{
  "key": "founder_tone",
  "value": "Be direct, practical, and execution-first.",
  "category": "preferences"
}
```

3. Add team member
- Method: `POST`
- URL: `/api/v1/memory/team`
- Headers:
  - `Authorization: Bearer <access_token>`
  - `Content-Type: application/json`
- Body:
```json
{
  "name": "Ravi",
  "role_title": "Backend Developer",
  "team": "tech",
  "reports_to_id": null,
  "skills": "Python, FastAPI, SQLAlchemy",
  "ai_level": 3,
  "current_project": "Nidin BOS API",
  "notes": "Owns backend stability",
  "user_id": null
}
```

4. Chat with agent (real AI)
- Method: `POST`
- URL: `/api/v1/agents/chat`
- Headers:
  - `Authorization: Bearer <access_token>`
  - `Content-Type: application/json`
- Body:
```json
{
  "message": "Give me top 3 priorities for today based on current team and memory.",
  "force_role": null
}
```

5. Get Gmail auth URL
- Method: `GET`
- URL: `/api/v1/email/auth-url`
- Headers:
  - `Authorization: Bearer <access_token>`
- Response includes `auth_url`. Open it in browser and complete OAuth.

6. Sync inbox
- Method: `POST`
- URL: `/api/v1/email/sync`
- Headers:
  - `Authorization: Bearer <access_token>`

7. List inbox
- Method: `GET`
- URL: `/api/v1/email/inbox?unread_only=false&limit=20`
- Headers:
  - `Authorization: Bearer <access_token>`
- Pick an `id` from the response for next steps.

8. Summarize an email
- Method: `POST`
- URL: `/api/v1/email/{id}/summarize`
- Headers:
  - `Authorization: Bearer <access_token>`

9. Draft reply (approval required, no auto-send)
- Method: `POST`
- URL: `/api/v1/email/{id}/draft-reply`
- Headers:
  - `Authorization: Bearer <access_token>`
  - `Content-Type: application/json`
- Body:
```json
{
  "instruction": "Keep it short, polite, and ask for next available meeting slot."
}
```

10. Review approvals before sending anything
- Method: `GET`
- URL: `/api/v1/approvals`
- Headers:
  - `Authorization: Bearer <access_token>`
