import { defineConfig, devices } from "@playwright/test";

// Uses the locally installed Chrome (channel) so no browser download is needed.
// The API (port 8000, WORKER_MODE=inprocess) and the web app (port 3100) must be running: `make demo`.
export default defineConfig({
  testDir: "./tests",
  timeout: 90_000,
  use: { baseURL: process.env.WEB_URL ?? "http://localhost:3100", channel: process.env.PW_CHANNEL ?? "chrome", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], channel: process.env.PW_CHANNEL ?? "chrome" } },
    { name: "mobile", use: { ...devices["Pixel 7"], channel: process.env.PW_CHANNEL ?? "chrome" } },
  ],
});
