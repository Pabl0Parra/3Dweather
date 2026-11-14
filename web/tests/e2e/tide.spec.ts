import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

// Needs the dev run in web/public/wx and the tide atlas in web/public/assets/globe
// (python -m pipeline tide-atlas --eot20 eot20/eot20.zip --out web/public/assets/globe).
const has = (p: string) => existsSync(fileURLToPath(new URL(`../../public/${p}`, import.meta.url)));
test.skip(!has("wx/latest.json") || !has("assets/globe/tide.json"), "dev run or tide atlas missing");

const FUNDY = "#45.00,-65.50,4.00";

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

const diff = (a: number[], b: number[]) => Math.max(...a.slice(0, 3).map((v, k) => Math.abs(v - b[k])));

async function clickCentre(page: Page) {
  const box = (await page.locator("#globe").boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
}

test("/tide-map shows the tide legend and the colour moves with the hour in the Bay of Fundy", async ({ page }) => {
  await open(page, "/tide-map", FUNDY);
  await expect(page.locator(".legend .lg-title")).toHaveText("Tide height");
  await expect(page.locator('nav[aria-label="Map layers"] a[aria-current="page"]')).toHaveAttribute("href", "/tide-map");
  await expect(page.locator("#credits")).toContainText("EOT20");
  const h0 = await pixel(page);
  await setHour(page, 3);
  const h3 = await pixel(page);
  expect(diff(h0, h3), `hour 0 ${h0} vs hour 3 ${h3}`).toBeGreaterThan(30);
});

test("tap readout gives a signed height and its direction in metres", async ({ page }) => {
  await open(page, "/tide-map", FUNDY);
  await clickCentre(page);
  await expect(page.locator(".probe-main")).toHaveText(/^Tide [+−]?\d+\.\d m, (rising|falling)$/);
});

test("tap readout and legend in feet", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("3dw.units", JSON.stringify({ length: "ft", speed: "kn", temp: "C" })));
  await open(page, "/tide-map", FUNDY);
  await clickCentre(page);
  await expect(page.locator(".probe-main")).toHaveText(/^Tide [+−]?\d+\.\d ft, (rising|falling)$/);
  await expect(page.locator(".legend")).toContainText("ft");
});

test("tab switch to the tide and back keeps working", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  await open(page, "/wave-map", FUNDY);
  const tabs = page.locator('nav[aria-label="Map layers"]');
  await tabs.getByRole("link", { name: "Tide" }).click();
  await page.waitForFunction(() => (window as any).__globe.layer() === "tide");
  await expect(page).toHaveURL(/\/tide-map\?debug&nosplash#45\.00,-65\.50,4\.00$/);
  await expect(page.locator(".legend .lg-title")).toHaveText("Tide height");
  await expect(page.locator("#biggest-button")).toHaveText("Highest tide now");
  await tabs.getByRole("link", { name: "Waves" }).click();
  await page.waitForFunction(() => (window as any).__globe.layer() === "waves");
  await expect(page.locator(".legend .lg-title")).toHaveText("Wave height");
  await setHour(page, 0);
  expect(errors).toEqual([]);
});

test("no seam at the antimeridian", async ({ page }) => {
  await open(page, "/tide-map", "#0.00,180.00,3.00");
  for (const dy of [-60, 0, 60]) {
    const w = await pixel(page, -2, dy), e = await pixel(page, 2, dy);
    expect(diff(w, e), `west ${w} east ${e} at dy ${dy}`).toBeLessThan(12);
  }
});

test("highest tide now flies to a sea point with a positive tide", async ({ page }) => {
  await open(page, "/tide-map", "#20.00,0.00,1.00");
  await page.locator("#biggest-button").click();
  await expect(page.locator(".probe-main")).toHaveText(/^Tide \+\d+\.\d m, (rising|falling)$/, { timeout: 10_000 });
});
