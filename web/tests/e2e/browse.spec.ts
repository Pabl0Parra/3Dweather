import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const hasCatalogue = existsSync(fileURLToPath(new URL("../../public/catalogue/countries.json", import.meta.url)));

test("the home page has search, near me, continents and popular places", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1")).toBeVisible();
  await expect(page.locator(".hero [data-search]")).toHaveCount(1);
  await expect(page.locator("button[data-near]")).toBeVisible();
  test.skip(!hasCatalogue, "catalogue missing");
  await expect(page.locator("details.continent summary", { hasText: "Europe" })).toHaveCount(1);
  expect(await page.locator(".popular a").count()).toBeGreaterThanOrEqual(8);
});

test.describe("browse pages", () => {
  test.skip(!hasCatalogue, "catalogue missing");

  test("a country lists its regions and filters them", async ({ page }) => {
    await page.goto("/us");
    await expect(page.locator("h1")).toContainText("United States");
    const ny = page.locator(".regions a", { hasText: "New York" });
    await expect(ny).toHaveAttribute("href", "/us/new-york");
    await page.locator(".filter").fill("flor");
    await expect(page.locator(".regions li:visible")).toHaveCount(1);
  });

  test("a region lists its places and links to them; the station links back", async ({ page }) => {
    await page.goto("/us/new-york");
    const nyc = page.getByRole("link", { name: "New York City", exact: true }).first();
    await expect(nyc).toHaveAttribute("href", "/us/new-york/new-york-city");
    await nyc.click();
    await expect(page.locator(".st-crumbs a", { hasText: "New York" })).toHaveAttribute("href", "/us/new-york");
    await expect(page.locator(".st-crumbs a", { hasText: "United States" })).toHaveAttribute("href", "/us");
  });

  test("near me lists the nearest places", async ({ page, context }) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({ latitude: 40.7, longitude: -74.0 });
    await page.goto("/");
    await page.locator("button[data-near]").click();
    await expect(page.locator(".near-list a").first()).toBeVisible();
    expect(await page.locator(".near-list a").count()).toBe(8);
  });

  test("browse pages fit a 320 px phone", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    for (const p of ["/", "/us", "/us/new-york"]) {
      await page.goto(p);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
    }
  });
});
