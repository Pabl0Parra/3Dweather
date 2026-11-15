import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const hasCatalogue = existsSync(fileURLToPath(new URL("../../public/catalogue/countries.json", import.meta.url)));

test.describe("finder", () => {
  test.skip(!hasCatalogue, "catalogue missing");

  test("the map shows clusters with OSM credit; a cluster zooms in; the list links to countries", async ({ page }) => {
    await page.route("https://tile.openstreetmap.org/**", (r) => r.fulfill({ status: 204 })); // no tile traffic in tests
    await page.goto("/stations");
    const map = page.locator("[data-finder]");
    await expect(map.locator(".leaflet-control-attribution")).toContainText("OpenStreetMap");
    await expect(map).toHaveAttribute("data-markers", /\d+/);
    const n = Number(await map.getAttribute("data-markers"));
    expect(n).toBeGreaterThan(5);
    expect(n).toBeLessThan(800);
    await map.locator(".cluster").first().click();
    await expect.poll(async () => Number(await map.getAttribute("data-markers"))).not.toBe(n);
    await expect(page.getByRole("link", { name: "United States", exact: true })).toHaveAttribute("href", "/us");
  });
});
