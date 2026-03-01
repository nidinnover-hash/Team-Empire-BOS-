# Nidin BOS

**Business Operating System** — AI agent platform for autonomous work operations.

Task orchestration, multi-integration management, and intelligent decision support with human-in-the-loop safety controls.

## Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy (async), Alembic
- **Frontend**: Server-rendered Jinja2 templates, vanilla JS, Lucide icons
- **Database**: PostgreSQL (SQLite for tests)
- **AI**: OpenAI, Groq, Anthropic (configurable per task)
- **Deployment**: Ubuntu/Nginx, Gunicorn, systemd

## Features

- Executive dashboard with real-time KPIs and intelligence layers
- Talk mode (conversational AI interface with context memory)
- Task and project management with priority automation
- Multi-integration hub: Gmail, Google Calendar, ClickUp, Slack, WhatsApp, GitHub, Notion, Stripe, Calendly, HubSpot, ElevenLabs, LinkedIn, Perplexity, Google Analytics
- Outgoing webhook management with HMAC signing and delivery logs
- Approval workflows with human-in-the-loop safety gates
- Compliance engine and CEO action center
- RBAC with MFA support
- Data hub (contacts, notes, goals, finance tracking)

## Quick Start

```bash
# Clone and setup
git clone https://github.com/nidinnover-hash/Nidin-BOS.git
cd Nidin-BOS
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in secrets

# Run migrations and start
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8002
```

## Testing

```bash
pytest tests/ -q          # 1052+ tests
ruff check app tests      # lint
npm run lint:frontend     # JS lint
```

## Docs

- [Production Runbook](docs/PRODUCTION_RUNBOOK.md)
- [Launch Checklist](docs/LAUNCH_CHECKLIST.md)
- [Error Handling Policy](docs/ERROR_HANDLING_POLICY.md)
- [Customization Guide](CUSTOMIZATION_GUIDE.md)

## Frontend

- Shared UI utilities in `app/static/js/ui-utils.js` (`PCUI.mapApiError`, `PCUI.setButtonLoading`, `PCUI.confirmDanger`)
- Visual regression tests via Playwright (`tests/ui/*.visual.spec.ts`)
- Release gate: `python scripts/check_ready.py`
