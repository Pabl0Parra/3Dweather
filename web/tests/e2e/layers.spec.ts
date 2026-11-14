import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

// Needs the reference run built into web/public/wx (see the plan's dev-data commands).
const HAS_DATA = existsSync(fileURLToPath(new URL("../../public/wx/latest.json", import.meta.url)));
test.skip(!HAS_DATA, "web/public/wx/latest.json missing: build the dev data first");

const SEA = [8, 26, 46];
const LAND = [27, 38, 54];

async function open(page: Page, path: string, hash: string) {
  await page.goto(`${path}?debug&nosplash${hash}`);
  await page.waitForFunction(() => (window as any).__globe?.ready === true, null, { timeout: 30_000 });
  await setHour(page, 0);
}

async function setHour(page: Page, h: number) {
  await page.evaluate(async (h) => {
    await (window as any).__globe.setHour(h);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  }, h);
}

async function pixel(page: Page, dx = 0, dy = 0): Promise<number[]> {
  return page.evaluate(([dx, dy]) => {
    const c = document.querySelector<HTMLCanvasElement>("canvas.globe-gl")!;
    const gl = c.getContext("webgl")!;
    const s = c.width / c.clientWidth;
    const x = Math.round((c.clientWidth / 2 + dx) * s), y = Math.round((c.clientHeight / 2 + dy) * s);
    const out = new Uint8Array(4);
    gl.readPixels(x, c.height - 1 - y, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, out);
    return [...out];
  }, [dx, dy]);
}

/** Far from both the plain sea and the plain land colour (limb shading allowed for). */
function painted(px: number[]): boolean {
  const off = (ref: number[]) => Math.max(...ref.map((v, k) => Math.abs(px[k] - v * 0.95)));
  return off(SEA) > 25 && off(LAND) > 25;
}

async function clickCentre(page: Page) {
  const box = (await page.locator("#globe").boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
}

const PAGES: [string, string, string][] = [
  ["/weather-map", "Rain", "#-0.23,-119.82,4"],
  ["/wind-map", "Wind speed", "#44.75,-140.45,4"],
  ["/temperature-map", "Air temperature", "#20,0,3"],
  ["/wave-map", "Wave height", "#44.28,-140.92,4"],
  ["/ocean-currents-map", "Current speed", "#-39.6,21.27,4"],
];

for (const [path, legend, hash] of PAGES) {
  test(`${path} loads with its legend and paints its layer`, async ({ page }) => {
    await open(page, path, hash);
    await expect(page.locator(".legend .lg-title")).toHaveText(legend);
    expect(painted(await pixel(page)), `${path} centre pixel ${await pixel(page)}`).toBe(true);
    await expect(page.locator('nav[aria-label="Map layers"] a[aria-current="page"]')).toHaveAttribute("href", path);
  });
}

test("wind and temperature are drawn over land", async ({ page }) => {
  await open(page, "/wind-map", "#40.4,-3.7,4");
  expect(painted(await pixel(page))).toBe(true);
  await open(page, "/temperature-map", "#40.4,-3.7,4");
  expect(painted(await pixel(page))).toBe(true);
});

test("a tab switch keeps the place and hour and updates the page", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  await open(page, "/wave-map", "#20.00,-30.00,2.00");
  await setHour(page, 30);
  await page.locator('nav[aria-label="Map layers"]').getByRole("link", { name: "Wind" }).click();
  await page.waitForFunction(() => (window as any).__globe.layer() === "wind");
  await expect(page).toHaveURL(/\/wind-map\?debug&nosplash#20\.00,-30\.00,2\.00$/);
  await expect(page).toHaveTitle("Wind map · 3Dweather");
  await expect(page.locator('nav[aria-label="Map layers"] a[aria-current="page"]')).toHaveText("Wind");
  await expect(page.locator(".legend .lg-title")).toHaveText("Wind speed");
  await expect(page.locator(".credits")).toContainText("ECMWF");
  await expect(page.getByRole("button", { name: "Strongest wind" })).toBeVisible();
  expect(await page.evaluate(() => (window as any).__globe.hour())).toBe(30);
  expect(errors).toEqual([]);
});

test("the wind readout at the run's wind peak reads a strong wind with gusts", async ({ page }) => {
  await open(page, "/wind-map", "#44.75,-140.45,4");
  await clickCentre(page);
  const probe = page.getByRole("dialog", { name: "Conditions here" });
  await expect(probe).toContainText(/Wind (\d+) kn from [NESW]{1,2}/);
  const kn = Number((await probe.textContent())!.match(/Wind (\d+) kn/)![1]);
  expect(kn).toBeGreaterThanOrEqual(50);
  await expect(probe).toContainText(/Gusts \d+ kn/);
});

test("the currents readout reads a current and the sea temperature", async ({ page }) => {
  await open(page, "/ocean-currents-map", "#-39.6,21.27,4");
  await clickCentre(page);
  const probe = page.getByRole("dialog", { name: "Conditions here" });
  await expect(probe).toContainText(/Current \d+\.\d kn toward [NESW]{1,2}/);
  await expect(probe).toContainText(/Sea \d+ °C/);
});

test("strongest wind flies to the manifest's wind peak", async ({ page }) => {
  await open(page, "/wind-map", "#20,0,1");
  await page.getByRole("button", { name: "Strongest wind" }).click();
  await page.waitForFunction(() => (window as any).__globe.view().zoom === 3.2, null, { timeout: 2500 });
  const v = await page.evaluate(() => (window as any).__globe.view());
  expect(Math.abs(v.lat0 - 44.75)).toBeLessThan(0.5);
  expect(Math.abs(v.lon0 - -140.45)).toBeLessThan(0.5);
});

test("a slow wave download never paints over the layer switched to", async ({ page }) => {
  await open(page, "/wind-map", "#20,-30,1");
  const want = await pixel(page);
  await page.route("**/globe-w*.webp", async (route) => {
    await new Promise((r) => setTimeout(r, 2500));
    await route.continue();
  });
  await page.goto("/wave-map?debug&nosplash#20,-30,1");
  await page.waitForFunction(() => (window as any).__globe?.info() !== null, null, { timeout: 15_000 });
  await page.locator('nav[aria-label="Map layers"]').getByRole("link", { name: "Wind" }).click();
  await page.waitForFunction(() => (window as any).__globe.ready === true, null, { timeout: 15_000 });
  await setHour(page, 0);
  await page.waitForTimeout(3500); // the wave chunks arrive meanwhile
  await setHour(page, 0);
  const got = await pixel(page);
  for (let k = 0; k < 3; k++) expect(Math.abs(got[k] - want[k])).toBeLessThanOrEqual(3);
});

test("at phone width the tabs scroll inside the header, not the page", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 740 });
  await open(page, "/weather-map", "#20,0,1");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await expect(page.locator('nav[aria-label="Map layers"] a')).toHaveCount(5);
});

test("switching clears the old layer's particles at once", async ({ page }) => {
  await open(page, "/wave-map", "#20,-30,1");
  await page.waitForTimeout(300);
  await page.route(/globe-[ab]\d\.webp/, async (route) => {
    await new Promise((r) => setTimeout(r, 3000));
    await route.continue();
  });
  await page.locator('nav[aria-label="Map layers"]').getByRole("link", { name: "Wind" }).click();
  await page.waitForTimeout(300);
  const lit = await page.evaluate(() => {
    const c = document.querySelector<HTMLCanvasElement>("canvas.globe-flow")!;
    const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
    let n = 0;
    for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++;
    return n;
  });
  expect(lit).toBe(0);
});

test("at phone width the active tab is scrolled into view", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 740 });
  await open(page, "/ocean-currents-map", "#20,0,1");
  const nav = (await page.locator('nav[aria-label="Map layers"]').boundingBox())!;
  const tab = (await page.locator('nav[aria-label="Map layers"] a[aria-current="page"]').boundingBox())!;
  expect(tab.x).toBeGreaterThanOrEqual(nav.x - 1);
  expect(tab.x + tab.width).toBeLessThanOrEqual(nav.x + nav.width + 1);
});
