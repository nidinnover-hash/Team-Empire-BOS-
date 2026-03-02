import { expect, test } from "@playwright/test";

/**
 * Smoke tests — verify each page loads without 500 errors.
 * These tests hit the login page (unauthenticated) and verify
 * authenticated pages redirect to login.
 */

const PUBLIC_PAGES = ["/web/login"];
const AUTH_PAGES = [
  "/",
  "/web/integrations",
  "/web/talk",
  "/web/tasks",
  "/web/webhooks",
  "/web/notifications",
  "/web/security",
  "/web/api-keys",
  "/web/audit",
  "/web/team",
  "/web/health",
];

test.describe("Public pages load", () => {
  for (const url of PUBLIC_PAGES) {
    test(`${url} returns 200`, async ({ page }) => {
      const response = await page.goto(url, { waitUntil: "domcontentloaded" });
      expect(response?.status()).toBe(200);
    });
  }
});

test.describe("Auth pages redirect to login when unauthenticated", () => {
  for (const url of AUTH_PAGES) {
    test(`${url} redirects to /web/login`, async ({ page }) => {
      await page.goto(url, { waitUntil: "domcontentloaded" });
      expect(page.url()).toContain("/web/login");
    });
  }
});
