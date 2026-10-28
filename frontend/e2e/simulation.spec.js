// F36 — every city: pick → Run → every tab, no console error, live counters move.
import { expect, test } from "@playwright/test";
import { API, cities, noErrorBanner, runCity, watchConsole } from "./helpers.js";

const TABS = ["Live Rescue", "Agents", "AI Assistant", "People", "Routes", "Prediction", "Dam", "Algorithms", "Report", "History"];
const ONLY = process.env.E2E_CITIES ? process.env.E2E_CITIES.split(",") : null;

test.describe("simulation page", () => {
  test("every city runs and every tab renders without errors", async ({ page, request }) => {
    const list = (await cities(request)).filter((c) => !ONLY || ONLY.includes(c.id));
    expect(list.length).toBeGreaterThan(0);
    for (const city of list) {
      await test.step(city.name, async () => {
        const con = watchConsole(page);
        await runCity(page, city.name);
        for (const tab of TABS) {
          await page.getByRole("tab", { name: new RegExp(tab) }).click();
          await expect(page.getByRole("tab", { name: new RegExp(tab) })).toHaveAttribute("aria-selected", "true");
          await page.waitForTimeout(800);
          await noErrorBanner(page);
        }
        // The engine's own state moves (the page polls the same endpoint).
        const t1 = (await (await request.get(`${API}/api/simulation/state`)).json()).tick;
        await page.waitForTimeout(5000);
        const s2 = await (await request.get(`${API}/api/simulation/state`)).json();
        expect(s2.city?.id || s2.params?.city).toBe(city.id);
        expect(s2.tick).toBeGreaterThan(t1);
        con.check();
      });
    }
  });

  test("what-if planner runs on the live state (F16)", async ({ page }) => {
    const con = watchConsole(page);
    await runCity(page, "Delhi");
    await page.getByRole("tab", { name: /Agents/ }).click();
    await page.getByRole("button", { name: "Run what-if" }).click();
    await expect(page.getByText(/Simulated from the live state at tick/)).toBeVisible({ timeout: 120_000 });
    await expect(page.getByRole("cell", { name: "No change" })).toBeVisible();
    con.check();
  });
});
