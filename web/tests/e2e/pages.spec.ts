import { expect, test } from "@playwright/test";

const PAGES: [string, RegExp][] = [
  ["/guides", /Guides/], ["/what-is-a-tide", /What is a tide/], ["/tidal-coefficient", /tidal coefficient/i],
  ["/solunar-times", /Solunar/], ["/about", /About/], ["/privacy", /Privacy/], ["/terms", /Terms/],
];

for (const [path, h1] of PAGES) {
  test(`${path} has its heading and the site footer`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator("h1")).toHaveText(h1);
    await expect(page.locator(".site-footer a", { hasText: "Privacy" })).toHaveAttribute("href", "/privacy");
  });
}

test("the guides index links every guide", async ({ page }) => {
  await page.goto("/guides");
  for (const p of ["/what-is-a-tide", "/tidal-coefficient", "/solunar-times"]) await expect(page.locator(`main a[href="${p}"]`)).toHaveCount(1);
});

test("about credits every data source", async ({ page }) => {
  await page.goto("/about");
  for (const s of ["NOAA", "ECMWF", "Open-Meteo", "EOT20", "GeoNames", "Natural Earth", "DE421", "OpenStreetMap"]) await expect(page.locator("main")).toContainText(s);
  await expect(page.locator("main")).toContainText("not NOAA's official predictions");
});
