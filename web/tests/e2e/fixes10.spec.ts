import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const hasCatalogue = existsSync(fileURLToPath(new URL("../../public/catalogue/countries.json", import.meta.url)));
const hasData = existsSync(fileURLToPath(new URL("../../station-data/us/new-york/new-york-city.json", import.meta.url)));

test("the home page has no duplicate ids and the hero search is labelled", async ({ page }) => {
  await page.goto("/");
  const dups = await page.evaluate(() => {
    const seen = new Map<string, number>();
    document.querySelectorAll("[id]").forEach((e) => seen.set(e.id, (seen.get(e.id) ?? 0) + 1));
    return [...seen].filter(([, n]) => n > 1).map(([id]) => id);
  });
  expect(dups).toEqual([]);
  await page.locator(".hero .search-button").click();
  await expect(page.locator(".hero input[type=search]")).toHaveAccessibleName(/Search tide stations/);
});

test("station pages link to the home page and the site's about, privacy and terms", async ({ page }) => {
  test.skip(!hasData, "station data missing");
  await page.goto("/us/new-york/new-york-city");
  await expect(page.locator(".brand")).toHaveAttribute("href", "/");
  for (const p of ["/about", "/privacy", "/terms"]) await expect(page.locator(`footer a[href="${p}"]`)).toHaveCount(1);
});

test("privacy names every stored choice", async ({ page }) => {
  await page.goto("/privacy");
  await expect(page.locator("main")).toContainText("wind speed");
  await expect(page.locator("main")).toContainText("temperature");
});

test("a finder popup stays open when the map moves", async ({ page }) => {
  test.skip(!hasCatalogue, "catalogue missing");
  await page.route("https://tile.openstreetmap.org/**", (r) => r.fulfill({ status: 204 }));
  await page.goto("/stations?debug");
  await expect(page.locator("[data-finder]")).toHaveAttribute("data-markers", /\d+/);
  await page.evaluate(() => (window as any).__finder.map.setView([40.75, -73.98], 15, { animate: false }));
  await expect.poll(() => page.evaluate(() => (window as any).__finder.singles())).toBeGreaterThan(0);
  await page.evaluate(() => (window as any).__finder.openFirstSingle());
  await expect(page.locator(".leaflet-popup-content a")).toHaveCount(1);
  await page.evaluate(() => (window as any).__finder.map.panBy([40, 0], { animate: false }));
  await page.waitForTimeout(200);
  await expect(page.locator(".leaflet-popup-content a")).toHaveCount(1);
});
