import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

// Needs the dev run (with regional files) in web/public/wx and the outlines in web/public/assets/globe/regions.
const has = (p: string) => existsSync(fileURLToPath(new URL(`../../public/${p}`, import.meta.url)));
test.skip(!has("wx/latest.json") || !has("assets/globe/regions/europe.json"), "dev run or regional outlines missing");

const SLUGS = ["united-states", "united-kingdom", "scotland", "ireland", "europe", "india", "west-pacific",
  "philippines", "australia", "new-zealand", "canada", "south-africa"];

async function open(page: Page, path: string) {
  await page.goto(`${path}?debug`);
  await page.waitForFunction(() => (window as any).__region?.ready === true, null, { timeout: 30_000 });
}

async function setHour(page: Page, h: number) {
  await page.evaluate(async (h) => {
    (window as any).__region.setHour(h);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  }, h);
}

/** Share of field-canvas pixels that are painted, and a fingerprint of the field. */
async function field(page: Page): Promise<{ painted: number; sig: number }> {
  return page.evaluate(() => {
    const c = document.querySelector<HTMLCanvasElement>("canvas.rm-field")!;
    const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
    let painted = 0, sig = 0;
    for (let i = 0; i < d.length; i += 4 * 97) {
      if (d[i + 3] > 0) painted++;
      sig = (sig * 31 + d[i] + 7 * d[i + 1] + 13 * d[i + 2] + 17 * d[i + 3]) % 1_000_000_007;
    }
    return { painted: painted / (d.length / (4 * 97)), sig };
  });
}

async function clickCentre(page: Page) {
  const box = (await page.locator("#region-map").boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
}

test("/weather-map/europe opens on rain and paints the field", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await open(page, "/weather-map/europe");
  await expect(page).toHaveTitle(/Europe weather map/);
  await expect(page.locator(".legend .lg-title")).toHaveText("Rain");
  await expect(page.locator('#rm-layers button[data-layer="rain"]')).toHaveAttribute("aria-pressed", "true");
  await setHour(page, 6);
  expect((await field(page)).painted).toBeGreaterThan(0.2); // cloud and rain over a good part of Europe
  await expect(page.locator(".rm-regions a")).toHaveCount(13);
  await expect(page.locator('.rm-regions a[aria-current="page"]')).toHaveText("Europe");
  expect(errors).toEqual([]);
});

test("the hour and the layer change the field", async ({ page }) => {
  await open(page, "/weather-map/europe");
  await setHour(page, 0);
  const h0 = await field(page);
  await setHour(page, 24);
  const h24 = await field(page);
  expect(h24.sig).not.toBe(h0.sig);
  await page.locator('#rm-layers button[data-layer="wind"]').click();
  await page.waitForFunction(() => (window as any).__region.layer() === "wind");
  await setHour(page, 24);
  const wind = await field(page);
  expect(wind.sig).not.toBe(h24.sig);
  await expect(page.locator(".legend .lg-title")).toHaveText("Wind speed");
  // Wind colours every grid cell (only the margin outside the grid stays clear); rain leaves dry cells clear.
  expect(wind.painted).toBeGreaterThan(0.8);
  expect(wind.painted).toBeGreaterThan(h24.painted);
});

test("tap readout gives rain and cloud, then wind", async ({ page }) => {
  await open(page, "/weather-map/europe");
  await setHour(page, 12);
  await clickCentre(page);
  await expect(page.locator(".probe-main")).toHaveText(/^(No rain|Rain \d+\.\d mm\/h)$/);
  await expect(page.locator(".probe")).toContainText(/Cloud \d+ %/);
  await page.locator('#rm-layers button[data-layer="wind"]').click();
  await expect(page.locator(".probe-main")).toHaveText(/^(Calm|Wind \d+ kn from [NESW]{1,2} \(\d+°\))$/);
});

test("/wind-map/europe opens on wind", async ({ page }) => {
  await open(page, "/wind-map/europe");
  await expect(page).toHaveTitle(/Europe wind map/);
  await expect(page.locator('#rm-layers button[data-layer="wind"]')).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".legend .lg-title")).toHaveText("Wind speed");
});

test("the strongest-wind line jumps to the peak on the map", async ({ page }) => {
  await open(page, "/weather-map/europe");
  const btn = page.locator('button[data-peak="wind"]');
  await expect(btn).toContainText(/Strongest wind\s+\d+ kn\s+on \w{3} \d+ \w{3}, \d\d:\d\d London time, (about \d+ km from|near) /);
  await btn.click();
  await page.waitForFunction(() => (window as any).__region.layer() === "wind");
  await expect(page.locator(".probe-main")).toHaveText(/^Wind \d+ kn from/);
});

test("every region page loads its map", async ({ page }) => {
  for (const slug of SLUGS) {
    await open(page, `/weather-map/${slug}`);
    const m = await page.evaluate(() => (window as any).__region.manifest());
    expect(m.region).toBe(slug);
    expect((await field(page)).painted).toBeGreaterThan(0);
  }
});

test("no horizontal page scroll on a 320 px phone", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await open(page, "/weather-map/europe");
  const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(sw).toBeLessThanOrEqual(cw);
});
