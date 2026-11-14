import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const HAS_DATA = existsSync(fileURLToPath(new URL("../../public/wx/latest.json", import.meta.url)));
test.skip(!HAS_DATA, "web/public/wx/latest.json missing: build the dev data first");

test.describe("with motion", () => {
  test.use({ reducedMotion: "no-preference" });

  test("plays on the first visit, then hands over to the live globe", async ({ page }) => {
    await page.goto("/wave-map?debug#20,0,1");
    await expect(page.locator(".splash")).toBeAttached();
    await expect(page.locator(".splash")).toHaveCount(0, { timeout: 4500 });
    await page.waitForFunction(() => (window as any).__globe?.ready === true);
    await expect(page.locator(".site-header")).toHaveCSS("opacity", "1");
  });

  test("plays only once per session", async ({ page }) => {
    await page.goto("/wave-map?debug#20,0,1");
    await expect(page.locator(".splash")).toHaveCount(0, { timeout: 4500 });
    await page.reload();
    await page.waitForFunction(() => (window as any).__globe?.ready === true);
    await expect(page.locator(".splash")).toHaveCount(0);
  });

  test("any key skips it", async ({ page }) => {
    await page.goto("/wave-map?debug#20,0,1");
    await expect(page.locator(".splash")).toBeAttached();
    await page.waitForTimeout(500);
    await page.keyboard.press("Shift");
    await expect(page.locator(".splash")).toHaveCount(0, { timeout: 300 });
  });

  test("a deep link ends on that place", async ({ page }) => {
    await page.goto("/wave-map?debug#40.4,-3.7,4");
    await expect(page.locator(".splash")).toHaveCount(0, { timeout: 4500 });
    const v = await page.evaluate(() => (window as any).__globe.view());
    expect(v.lat0).toBeCloseTo(40.4, 6);
    expect(v.lon0).toBeCloseTo(-3.7, 6);
    expect(v.zoom).toBe(4);
  });

  test("a failing forecast still ends the splash with the retry notice", async ({ page }) => {
    await page.route("**/globe-w*.webp", (route) => route.abort());
    await page.goto("/wave-map?debug#20,0,1");
    await expect(page.locator(".splash")).toHaveCount(0, { timeout: 5000 });
    await expect(page.getByText("Couldn't load the forecast")).toBeVisible();
  });

  test("no console errors during the splash", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("/wave-map?debug#20,0,1");
    await expect(page.locator(".splash")).toHaveCount(0, { timeout: 4500 });
    expect(errors).toEqual([]);
  });
});

test("reduced motion gets a short fade only", async ({ page }) => {
  await page.goto("/wave-map?debug#20,0,1");
  await expect(page.locator(".splash")).toHaveCount(0, { timeout: 800 });
});
