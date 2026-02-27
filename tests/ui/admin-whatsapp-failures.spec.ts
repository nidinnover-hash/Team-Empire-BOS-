import { expect, test } from "@playwright/test";

test("admin WhatsApp failures panel toggles independently and handles API errors", async ({ page }) => {
  let readinessDetailCalls = 0;
  const waDaysCalls: number[] = [];

  await page.route("**/web/admin**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/html",
      body: `<!doctype html>
<html><body>
  <div id="loading-orgs"></div><div id="loading-users"></div><div id="loading-readiness"></div>
  <div id="k-orgs"></div><div id="k-users"></div><div id="k-tasks"></div><div id="k-active"></div>
  <select id="fleet-status-filter"><option value="">All</option></select>
  <table><tbody id="orgs-body"></tbody></table>
  <table><tbody id="readiness-body"></tbody></table>
  <table><tbody id="users-body"></tbody></table>
  <div id="readiness-detail-empty"></div>
  <div id="readiness-detail" style="display:none">
    <div id="detail-org-name"></div>
    <div id="detail-score"></div>
    <div id="detail-status"></div>
    <div id="detail-allowed-modes"></div>
    <div id="detail-denied-modes"></div>
    <ul id="detail-reasons"></ul>
    <div id="policy-msg"></div><div id="rollout-msg"></div><div id="dryrun-msg"></div>
    <div id="policy-meta"></div>
    <select id="policy-current-mode"><option value="approved_execution">approved_execution</option></select>
    <input id="policy-allow-auto" type="checkbox" />
    <input id="policy-min-auto" />
    <input id="policy-min-approved" />
    <input id="policy-min-autonomous" />
    <input id="policy-block-alerts" type="checkbox" />
    <input id="policy-block-stale" type="checkbox" />
    <input id="policy-block-sla" type="checkbox" />
    <button id="policy-save-btn" type="button"></button>
    <tbody id="policy-history-body"></tbody>
    <select id="policy-template-select"></select>
    <button id="policy-template-apply-btn" type="button"></button>
    <div id="policy-template-desc"></div>
    <input id="rollout-kill-switch" type="checkbox" />
    <input id="rollout-max-actions" />
    <input id="rollout-pilot-orgs" />
    <button id="rollout-save-btn" type="button"></button>
    <input id="dryrun-approval-type" />
    <button id="dryrun-run-btn" type="button"></button>
    <ul id="dryrun-reasons"></ul>
    <div class="trend-head">
      <div class="trend-controls">
        <button class="trend-btn active" data-days="7" type="button">7d</button>
        <button class="trend-btn" data-days="14" type="button">14d</button>
        <button class="trend-btn" data-days="30" type="button">30d</button>
      </div>
    </div>
    <table><tbody id="trend-body"></tbody></table>
  </div>
  <script src="/static/js/admin-page.js"></script>
</body></html>`,
    });
  });

  await page.route("**/web/api-token", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ token: "test-token" }) });
  });

  await page.route("**/api/v1/admin/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/v1/admin/orgs") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ id: 1, name: "Org 1", slug: "org-1", user_count: 1, task_count: 2, approval_count: 0, last_activity_at: "2026-02-27T10:00:00Z" }]) });
      return;
    }
    if (path === "/api/v1/admin/users") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
      return;
    }
    if (path === "/api/v1/admin/orgs/readiness") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ org_id: 1, org_name: "Org 1", score: 84, status: "ready", blocker_count: 0, generated_at: "2026-02-27T10:00:00Z" }]) });
      return;
    }
    if (path === "/api/v1/admin/orgs/1/readiness") {
      readinessDetailCalls += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ org_id: 1, org_name: "Org 1", score: 84, status: "ready", blockers: [], recommendations: [], metrics: [], generated_at: "2026-02-27T10:00:00Z" }) });
      return;
    }
    if (path === "/api/v1/admin/orgs/1/autonomy-gates") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ org_id: 1, org_name: "Org 1", readiness_score: 84, readiness_status: "ready", allowed_modes: ["suggest_only", "approved_execution"], denied_modes: ["autonomous"], reasons: [], generated_at: "2026-02-27T10:00:00Z" }) });
      return;
    }
    if (path === "/api/v1/admin/orgs/1/readiness/trend") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ org_id: 1, org_name: "Org 1", days: 7, series: [{ day: "2026-02-27", integration_failures: 0, high_alerts_created: 0, pending_approvals_created: 0 }], generated_at: "2026-02-27T10:00:00Z" }) });
      return;
    }
    if (path === "/api/v1/admin/orgs/1/autonomy-policy") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ current_mode: "approved_execution", allow_auto_approval: false, min_readiness_for_auto_approval: 70, min_readiness_for_approved_execution: 65, min_readiness_for_autonomous: 90, block_on_unread_high_alerts: true, block_on_stale_integrations: true, block_on_sla_breaches: true, updated_at: null, updated_by_user_id: null, updated_by_email: null }) });
      return;
    }
    if (path === "/api/v1/admin/orgs/1/autonomy-policy/history") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
      return;
    }
    if (path === "/api/v1/admin/orgs/1/autonomy-rollout") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ kill_switch: false, pilot_org_ids: [], max_actions_per_day: 250 }) });
      return;
    }
    if (path === "/api/v1/admin/orgs/1/autonomy-policy/templates") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
      return;
    }
    if (path === "/api/v1/admin/orgs/1/whatsapp-webhook-failures") {
      const days = Number(url.searchParams.get("days") || "7");
      waDaysCalls.push(days);
      if (days === 7 && waDaysCalls.length >= 3) {
        await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "boom" }) });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          org_id: 1,
          org_name: "Org 1",
          days,
          total: days === 1 ? 1 : 3,
          failures: [
            { event_id: 1, event_type: "whatsapp_webhook_failed", error_code: "signature_verification_failed", detail: "invalid", phone_number_id: "pn-1", actor_user_id: null, created_at: "2026-02-27T10:00:00Z" },
          ],
          generated_at: "2026-02-27T10:00:00Z",
        }),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "not found" }) });
  });

  await page.goto("/web/admin", { waitUntil: "networkidle" });

  await expect(page.locator("#wa-failures-total")).toHaveText("3");
  await expect(page.locator(".trend-btn:not(.wa-failures-btn)[data-days='7']")).toHaveClass(/active/);
  await expect(page.locator(".trend-btn:not(.wa-failures-btn)[data-days='14']")).not.toHaveClass(/active/);

  const readinessCallsAfterLoad = readinessDetailCalls;
  await page.locator(".wa-failures-btn[data-days='1']").click();
  await expect(page.locator("#wa-failures-total")).toHaveText("1");
  expect(readinessDetailCalls).toBe(readinessCallsAfterLoad);

  await page.locator(".wa-failures-btn[data-days='7']").click();
  await expect(page.locator("#wa-failures-body")).toContainText("Failed to load failures");
});
