// F36 — browser tests. Needs the dev dependency @playwright/test (+ `npx playwright install chromium`);
// it is NOT installed until the authors approve it. Run with `npm run e2e`.
// Reuses a running backend (:8000) and vite (:5173), or starts them.
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 240_000,
  expect: { timeout: 30_000 },
  workers: 1, // one engine = one live run: specs must not overlap
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5173",
    // Playwright pages are visible (document.hidden = false), so the live feed does not pause.
    viewport: { width: 1400, height: 900 },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "powershell -ExecutionPolicy Bypass -File ../start-backend.ps1",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: true,
      timeout: 180_000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
