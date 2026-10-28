// F36 — phone pages: /sos validation + offline queue, /safe.
import { expect, test } from "@playwright/test";
import { noErrorBanner, watchConsole } from "./helpers.js";

test.use({ viewport: { width: 390, height: 844 }, permissions: ["geolocation"], geolocation: { latitude: 28.62, longitude: 77.23 } });

test("/sos refuses to send without a location", async ({ page }) => {
  const con = watchConsole(page);
  await page.goto("/sos");
  await expect(page.getByRole("heading", { name: "Ask for rescue" })).toBeVisible();
  await page.getByLabel("Your name").fill("E2E Test");
  await page.getByRole("button", { name: /Send SOS/ }).click();
  await expect(page.locator(".drv-banner.is-error")).toBeVisible();
  con.check();
});

test("/sos keeps the SOS on the phone while offline (production build only)", async ({ page, context }) => {
  test.skip(!process.env.E2E_PROD, "the service worker registers in production builds only (npx vite build && npx vite preview)");
  await page.goto("/sos");
  await page.getByLabel("Your name").fill("E2E Offline");
  await page.getByRole("button", { name: /Share my location/ }).click();
  await context.setOffline(true);
  await page.getByRole("button", { name: /Send SOS/ }).click();
  await expect(page.getByText(/No connection — your SOS is saved on this phone/)).toBeVisible();
  await context.setOffline(false);
});

test("/safe shows the safety view for the phone's location", async ({ page }) => {
  const con = watchConsole(page);
  await page.goto("/safe");
  await expect(page.getByRole("heading", { name: "Am I safe?" })).toBeVisible();
  await page.getByRole("button", { name: /location/i }).first().click();
  await expect(page.locator("h2").first()).toBeVisible();
  await noErrorBanner(page);
  con.check();
});
