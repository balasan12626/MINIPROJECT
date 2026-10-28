// F36 — driver app in manual accept mode: Accept moves the job on, Reject hands it to another unit.
import { expect, test } from "@playwright/test";
import { API, runCity, watchConsole } from "./helpers.js";

async function assignedUnit(request) {
  for (let i = 0; i < 60; i += 1) {
    const s = await (await request.get(`${API}/api/simulation/state`)).json();
    const row = (s.contact_log || []).find((r) => r.ops_status === "assigned" && r.unit_name);
    if (row) return row.unit_name;
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("no job reached 'assigned' in 60 s");
}

test("manual mode: accept and reject from the driver page", async ({ page, request }) => {
  const con = watchConsole(page);
  await runCity(page, "Delhi");
  expect((await request.post(`${API}/api/simulation/accept-mode`, { data: { mode: "manual" } })).ok()).toBeTruthy();

  const unit = await assignedUnit(request);
  const driver = await page.context().newPage();
  await driver.setViewportSize({ width: 390, height: 844 });
  await driver.goto(`/driver/${encodeURIComponent(unit)}`);
  await driver.getByRole("button", { name: /Accept/ }).click();
  await expect(driver.getByText(/en route|Driving|picked up|No job/i).first()).toBeVisible();

  const other = await assignedUnit(request);
  await driver.goto(`/driver/${encodeURIComponent(other)}`);
  await driver.getByRole("button", { name: /Reject/ }).click();
  const s = await (await request.get(`${API}/api/simulation/state`)).json();
  const rejected = (s.contact_log || []).some((r) => (r.rejected_units || []).includes(other));
  expect(rejected).toBeTruthy();

  await request.post(`${API}/api/simulation/accept-mode`, { data: { mode: "auto" } });
  con.check();
});
