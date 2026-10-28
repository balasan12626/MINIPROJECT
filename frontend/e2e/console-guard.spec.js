// F36 — proves the guard works: a page that logs a console error must FAIL the check.
import { expect, test } from "@playwright/test";
import { watchConsole } from "./helpers.js";

test("a console error fails the console check", async ({ page }) => {
  const con = watchConsole(page);
  await page.goto("/sos");
  await page.evaluate(() => console.error("deliberate e2e fixture error"));
  await page.waitForTimeout(200);
  expect(con.errors.some((e) => e.includes("deliberate e2e fixture error"))).toBe(true);
  expect(() => con.check()).toThrow();
});
