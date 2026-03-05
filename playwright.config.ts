import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

function loadDotEnvIfPresent(): void {
  const envPath = path.resolve(__dirname, ".env");
  if (!fs.existsSync(envPath)) return;
  const lines = fs.readFileSync(envPath, "utf8").split(/\r?\n/);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const [key, ...rest] = line.split("=");
    const envKey = key.trim();
    if (!envKey || process.env[envKey]) continue;
    process.env[envKey] = rest.join("=").trim();
  }
}

loadDotEnvIfPresent();

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "./tests/ui",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 7"] },
    },
  ],
});
