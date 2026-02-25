# Frontend Quality Checks

## Project Customization Guide
- See [`CUSTOMIZATION_GUIDE.md`](CUSTOMIZATION_GUIDE.md) for a full map of what to edit for config, APIs, layers, compliance, clone training, UI, and DB migrations.

## Shared UI utilities
- `app/static/js/ui-utils.js` centralizes:
  - API error mapping (`PCUI.mapApiError`)
  - consistent button loading states (`PCUI.setButtonLoading`)
  - destructive confirmation wrapper (`PCUI.confirmDanger`)

## Visual regression tests
- Playwright config: `playwright.config.ts`
- Specs: `tests/ui/*.visual.spec.ts`
- Run locally:
  1. Start backend on `http://127.0.0.1:8000`
  2. Install Playwright test runner in your JS toolchain
  3. Run `npx playwright test tests/ui --update-snapshots` for first baseline
  4. Run `npx playwright test tests/ui` in CI for diff detection

## Release gate
- Linux/macOS/CI: `python scripts/check_ready.py`
- Windows PowerShell: `.\scripts\check_ready.ps1`

## Launch docs
- [Launch checklist](docs/LAUNCH_CHECKLIST.md)
- [Production runbook](docs/PRODUCTION_RUNBOOK.md)
