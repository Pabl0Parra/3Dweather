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
  await page.route("**/globe-w0.webp", (route) => route.abort());
  await page.goto("/wave-map?debug#40.4,-3.7,4");
  await expect(page.getByText("Couldn't load the forecast")).toBeVisible({ timeout: 15_000 });
  await page.waitForFunction(() => (window as any).__globe?.drawn === true);
  const [r, g, b] = await pixel(page);
  for (const [got, want] of [[r, 27], [g, 38], [b, 54]]) expect(Math.abs(got - want)).toBeLessThanOrEqual(12);
});

test("no console errors on load", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  await open(page, "#20,0,1");
  expect(errors).toEqual([]);
});
