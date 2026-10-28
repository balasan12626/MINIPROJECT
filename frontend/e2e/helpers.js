import { expect } from "@playwright/test";

export const API = process.env.E2E_API || "http://127.0.0.1:8000";

/** Collect console errors + uncaught page errors; `check()` fails the test on any. */
export function watchConsole(page, ignore = []) {
  const errors = [];
  const skip = (t) => ignore.some((re) => re.test(t)) || /favicon|tile\.openstreetmap|ResizeObserver loop/i.test(t);
  page.on("console", (m) => {
    if (m.type() === "error" && !skip(m.text())) errors.push(`console: ${m.text()}`);
  });
  page.on("pageerror", (e) => {
    if (!skip(String(e))) errors.push(`pageerror: ${e}`);
  });
  return {
    errors,
    check: () => expect(errors, errors.join("\n")).toEqual([]),
  };
}

/** No error banner of the app anywhere on the page. */
export async function noErrorBanner(page) {
  await expect(page.getByText(/DATA UNAVAILABLE|Something went wrong|Request failed with status code 5/)).toHaveCount(0);
}

export async function cities(request) {
  const r = await request.get(`${API}/api/cities`);
  expect(r.ok()).toBeTruthy();
  const body = await r.json();
  return body.cities || body;
}

/** Pick a city on Setup, press RUN SCENARIO, wait for the first live tick. */
export async function runCity(page, cityName) {
  await page.goto("/simulation?tab=setup");
  const exact = new RegExp(`^${cityName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`);
  await page.locator(".city-card", { has: page.locator("strong", { hasText: exact }) }).click();
  await page.getByRole("button", { name: /RUN SCENARIO/ }).first().click();
  await expect(page.getByText(/Results ready|Re-run/).first()).toBeVisible({ timeout: 180_000 });
}
