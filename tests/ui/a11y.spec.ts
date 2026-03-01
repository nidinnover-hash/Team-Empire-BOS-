import { expect, test } from "@playwright/test";
import { injectAxe, checkA11y } from "@axe-core/playwright";

test("public pages have no critical accessibility violations", async ({ page }) => {
  const urls = ["/", "/web/login"];

  for (const url of urls) {
    await page.goto(url, { waitUntil: "networkidle" });
    await injectAxe(page);
    await checkA11y(page, undefined, {
      detailedReport: true,
      detailedReportOptions: { html: true },
      axeOptions: {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa"],
        },
      },
    });
    await expect(page).toHaveTitle(/.+/);
  }
});
