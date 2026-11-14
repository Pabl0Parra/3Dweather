import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { colourAt } from "../../src/globe/ramp";

// Needs the reference run built into web/public/wx (see the plan's dev-data commands).
const HAS_DATA = existsSync(fileURLToPath(new URL("../../public/wx/latest.json", import.meta.url)));
test.skip(!HAS_DATA, "web/public/wx/latest.json missing: build the dev data first");

async function open(page: Page, hash: string) {
  await page.goto(`/wave-map?debug${hash}`);
  await page.waitForFunction(() => (window as any).__globe?.ready === true, null, { timeout: 30_000 });
  await setHour(page, 0);
}

/** Jump to a forecast hour and wait for the frame it causes to be drawn. */
async function setHour(page: Page, h: number) {
  await page.evaluate(async (h) => {
    await (window as any).__globe.setHour(h);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  }, h);
}

/** RGBA of the WebGL canvas at an offset from its centre (CSS px). */
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

test("open sea at the reference peak shows the top of the ramp", async ({ page }) => {
  await open(page, "#44.28,-140.92,4");
  const got = await pixel(page);
  // Reference run peak is 13.9 m here; expect the ramp colour blended over the sea.
  const sea = [8, 26, 46];
  const c = colourAt(13.9), a = c[3] / 255;
  for (let k = 0; k < 3; k++) expect(Math.abs(got[k] - (sea[k] * (1 - a) + c[k] * a))).toBeLessThanOrEqual(12);
  expect(got[0]).toBeGreaterThan(200);
});

test("land is drawn in the land colour", async ({ page }) => {
  await open(page, "#40.4,-3.7,4");
  const [r, g, b] = await pixel(page);
  for (const [got, want] of [[r, 27], [g, 38], [b, 54]]) expect(Math.abs(got - want)).toBeLessThanOrEqual(12);
});

test("no seam at the antimeridian", async ({ page }) => {
  await open(page, "#0,180,4");
  const left = await pixel(page, -2, 0), right = await pixel(page, 2, 0);
  for (let k = 0; k < 3; k++) expect(Math.abs(left[k] - right[k])).toBeLessThanOrEqual(6);
});

test("a failed sprite shows the retry notice and still draws land", async ({ page }) => {
  // Every chunk: the timeline opens at the current hour, which may be in any chunk.
  await page.route("**/globe-w*.webp", (route) => route.abort());
  await page.goto("/wave-map?debug#40.4,-3.7,4");
  await expect(page.getByText("Couldn't load the forecast")).toBeVisible({ timeout: 15_000 });
  await page.waitForFunction(() => (window as any).__globe?.drawn === true);
  const [r, g, b] = await pixel(page);
  for (const [got, want] of [[r, 27], [g, 38], [b, 54]]) expect(Math.abs(got - want)).toBeLessThanOrEqual(12);
});

test("dragging right moves the hash longitude west", async ({ page }) => {
  await open(page, "#20,0,1");
  const box = (await page.locator("#globe").boundingBox())!;
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 200, cy, { steps: 10 });
  await page.waitForTimeout(150); // hold still so there is no inertia
  await page.mouse.up();
  await page.waitForFunction(() => /^#20\.00,-\d/.test(location.hash), null, { timeout: 1500 });
});

test("the wheel does not zoom before the map is clicked", async ({ page }) => {
  await open(page, "#20,0,1");
  const box = (await page.locator("#globe").boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, -400);
  await expect(page.getByText("Click the map to zoom with the wheel")).toBeVisible();
  expect(await page.evaluate(() => (window as any).__globe.view().zoom)).toBe(1);
});

test("a malformed hash falls back to the default view", async ({ page }) => {
  await open(page, "#abc");
  expect(await page.evaluate(() => (window as any).__globe.view())).toEqual({ lat0: 20, lon0: 0, zoom: 1 });
});

test("Space starts playback and the slider moves", async ({ page }) => {
  await open(page, "#20,0,1");
  const slider = page.locator(".tl-slider");
  const before = Number(await slider.inputValue());
  await page.locator("body").press("Space");
  await expect.poll(async () => Number(await slider.inputValue()), { timeout: 2000 }).toBeGreaterThan(before);
});

test("frames blend between forecast steps", async ({ page }) => {
  await open(page, "#44.28,-140.92,4");
  const at0 = await pixel(page);
  await setHour(page, 4.5);
  const at45 = await pixel(page);
  expect(at45.slice(0, 3)).not.toEqual(at0.slice(0, 3));
});

test("the timeline label and legend are shown", async ({ page }) => {
  await open(page, "#20,0,1");
  await expect(page.locator(".tl-label")).toHaveText(/^\w{3} \d{1,2} \w{3}, 06:00 · /);
  await expect(page.locator(".legend")).toContainText("Wave height");
});

test("without WebGL the page says so instead of staying blank", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript(() => {
    const orig = HTMLCanvasElement.prototype.getContext;
    (HTMLCanvasElement.prototype as any).getContext = function (this: HTMLCanvasElement, type: string, ...rest: unknown[]) {
      return type.startsWith("webgl") ? null : (orig as any).call(this, type, ...rest);
    };
  });
  await page.goto("/wave-map#20,0,1");
  await expect(page.locator("#globe")).toContainText("needs WebGL");
  expect(errors).toEqual([]);
});

test("particle trails are drawn over the sea", async ({ page }) => {
  await open(page, "#20,-30,1");
  await page.waitForTimeout(300);
  const lit = await page.evaluate(() => {
    const c = document.querySelector<HTMLCanvasElement>("canvas.globe-flow")!;
    const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
    let n = 0;
    for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++;
    return n;
  });
  expect(lit).toBeGreaterThan(200);
});

test("no console errors on load", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  await open(page, "#20,0,1");
  expect(errors).toEqual([]);
});
