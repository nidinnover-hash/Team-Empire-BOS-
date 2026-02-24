# Frontend Quality Checks

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
