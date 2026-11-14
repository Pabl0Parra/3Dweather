import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

// Needs the built catalogue in web/public/catalogue (python -m pipeline catalogue --out web/public/catalogue).
const has = (p: string) => existsSync(fileURLToPath(new URL(`../../public/${p}`, import.meta.url)));
test.skip(!has("catalogue/stations.json"), "catalogue missing");

test("the New York City page", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const res = await page.goto("/us/new-york/new-york-city");
  expect(res?.status()).toBe(200);
  await expect(page).toHaveTitle("New York City tide times and weather · 3Dweather");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("New York City");
  await expect(page.locator(".st-crumbs")).toHaveText(/United States\s*\/\s*New York/);
  await expect(page.locator(".st-facts")).toContainText("America/New_York");
  await expect(page.getByRole("link", { name: "Waves on the globe" })).toHaveAttribute("href", "/wave-map#40.71,-74.01,6.0");
  await expect(page.getByRole("link", { name: "United States weather map" })).toHaveAttribute("href", "/weather-map/united-states");
  const near = page.locator(".st-near a");
  await expect(near).toHaveCount(8);
  const href = await near.first().getAttribute("href");
  await near.first().click();
  await expect(page).toHaveURL(new RegExp(`${href}$`));
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText("New York City");
  expect(errors).toEqual([]);
});

test("a NOAA gauge page", async ({ page }) => {
  await page.goto("/us/hawaii/port-allen-hanapepe-bay");
  await expect(page.locator(".st-lede")).toHaveText("NOAA tide gauge 1611347 in Hawaii, United States.");
});

test("a station page fits a 320 px phone", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto("/us/new-york/new-york-city");
  const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(sw).toBeLessThanOrEqual(cw);
});
