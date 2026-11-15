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
  await expect(page.locator(".st-place")).toContainText("America/New_York");
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

// Phase 9: pages built with daily station data (python -m pipeline station-data --out web/station-data).
const hasData = (p: string) => existsSync(fileURLToPath(new URL(`../../station-data/${p}.json`, import.meta.url)));

test.describe("station data", () => {
  test.skip(!hasData("us/new-york/new-york-city"), "station data missing");

  test("New York City shows today's tides, the month and its donor", async ({ page }) => {
    await page.goto("/us/new-york/new-york-city");
    const rows = page.locator(".st-month tbody tr");
    const n = await rows.count();
    expect(n).toBeGreaterThanOrEqual(28);
    expect(n).toBeLessThanOrEqual(31);
    await expect(page.locator(".st-month tbody tr.today")).toHaveCount(1);
    expect(await page.locator(".st-turns li").count()).toBeGreaterThanOrEqual(3);
    await expect(page.locator(".st-source")).toContainText("taken from");
    await expect(page.locator(".st-source")).toContainText("not NOAA's official predictions");
    await expect(page.locator(".st-sky")).toContainText("Sunrise");
  });

  test("the chart is drawn, a picked day redraws it and the unit switch changes heights", async ({ page }) => {
    await page.goto("/us/new-york/new-york-city");
    const curve = page.locator("svg[data-chart] path[data-curve]");
    await expect(curve).toHaveCount(1);
    const before = await curve.getAttribute("d");
    expect(before!.split("L").length).toBeGreaterThan(100);
    await expect(page.locator("svg[data-chart] [data-now]")).toHaveCount(1);
    const other = page.locator(".st-month tbody tr:not(.today) button[data-pick]").first();
    const label = (await other.textContent())!;
    await other.click();
    await expect(page.locator("[data-day-label]")).toHaveText(label);
    await expect.poll(() => curve.getAttribute("d")).not.toBe(before);
    await expect(page.locator("svg[data-chart] [data-now]")).toHaveCount(0);
    await expect(page.locator(".st-turns li span").first()).toContainText(" m");
    await page.locator("button[data-unit=ft]").click();
    await expect(page.locator(".st-turns li span").first()).toContainText(" ft");
    await expect(page.locator(".st-month tbody span[data-h]").first()).toContainText(" ft");
    await page.reload();
    await expect(page.locator(".st-turns li span").first()).toContainText(" ft"); // remembered
  });

  test("a place without tides says so", async ({ page }) => {
    test.skip(!hasData("us/north-carolina/jacksonville"), "no-tide station data missing");
    await page.goto("/us/north-carolina/jacksonville");
    await expect(page.locator(".st-none")).toContainText("No tide predictions here");
    await expect(page.locator(".st-turns")).toHaveCount(0);
    await expect(page.locator(".st-sky")).toContainText("Sunrise");
  });
});
