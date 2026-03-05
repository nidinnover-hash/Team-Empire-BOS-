import { APIResponse, expect, Page } from "@playwright/test";

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value || !value.trim()) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value.trim();
}

export async function loginForVisuals(page: Page): Promise<void> {
  const username =
    process.env.PLAYWRIGHT_LOGIN_EMAIL?.trim() ||
    process.env.ADMIN_EMAIL?.trim() ||
    "demo@ai.com";
  const password =
    process.env.PLAYWRIGHT_LOGIN_PASSWORD?.trim() ||
    process.env.ADMIN_PASSWORD?.trim();

  if (!password) {
    requiredEnv("PLAYWRIGHT_LOGIN_PASSWORD");
  }

  const totp = process.env.PLAYWRIGHT_LOGIN_TOTP?.trim();

  const submitLogin = async (organizationId?: string): Promise<APIResponse> => {
    return page.request.post("/web/login", {
      form: {
        username,
        password: password as string,
        ...(totp ? { totp_code: totp } : {}),
        ...(organizationId ? { organization_id: organizationId } : {}),
      },
    });
  };

  let response = await submitLogin();
  if (!response.ok()) {
    const payload = await response.json().catch(() => ({} as Record<string, unknown>));
    const detail = payload?.detail as Record<string, unknown> | string | undefined;
    const detailCode = typeof detail === "object" && detail ? String(detail.code || "") : "";
    const organizations =
      typeof detail === "object" && detail && Array.isArray(detail.organizations) ? detail.organizations : [];

    if (detailCode === "org_selection_required" && organizations.length > 0) {
      const firstOrg = organizations[0] as Record<string, unknown>;
      const orgId = String(firstOrg.id || "");
      if (orgId) {
        response = await submitLogin(orgId);
      }
    }

    if (!response.ok()) {
      const retryPayload = await response.json().catch(() => ({} as Record<string, unknown>));
      const retryText = JSON.stringify(retryPayload);
      const mfaRequired =
        response.headers()["x-mfa-required"] === "true" ||
        retryText.toLowerCase().includes("mfa code required");
      if (mfaRequired && !totp) {
        throw new Error("Login requires MFA. Set PLAYWRIGHT_LOGIN_TOTP for visual tests.");
      }
      throw new Error(`Playwright login failed (${response.status()}): ${retryText}`);
    }
  }

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page).not.toHaveURL(/\/web\/login/);
}
