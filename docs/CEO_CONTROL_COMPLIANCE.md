# CEO Control + Compliance

This layer is **suggest-only**. It never blocks deployment, deletes resources, or executes irreversible actions.

## Environment Variables

- `GITHUB_APP_ID`
- `GITHUB_PRIVATE_KEY_PEM` (use `\n` escapes in `.env`)
- `GITHUB_ORG` (example: `EmpireO.AI`)
- `CRITICAL_GITHUB_REPOS` (comma-separated: `EmpireO.AI/core,EmpireO.AI/api`)
- `CLICKUP_CRITICAL_FOLDER_NAME` (default: `🔴 Critical Systems`)
- `CLICKUP_CEO_PRIORITY_TAG` (default: `CEO-PRIORITY`)
- `DIGITALOCEAN_BASE_URL` (default: `https://api.digitalocean.com/v2`)

## New APIs

- `POST /api/v1/integrations/github/discover-installation`
- `POST /api/v1/integrations/digitalocean/connect`
- `GET /api/v1/integrations/digitalocean/status`
- `POST /api/v1/integrations/digitalocean/sync`
- `GET /api/v1/control/ceo/status`
- `POST /api/v1/control/compliance/run`
- `GET /api/v1/control/compliance/report`
- `POST /api/v1/control/message-draft`

## Scheduler

- Hourly sync path includes GitHub, ClickUp, DigitalOcean (read-only) plus compliance run.
- Daily `09:00 Asia/Kolkata` stores CEO summary snapshot in `ceo_summaries`.

## Running

1. Run migrations:
   - `python -m alembic upgrade head`
2. Trigger compliance manually:
   - `POST /api/v1/control/compliance/run`
3. Fetch latest report:
   - `GET /api/v1/control/compliance/report`
