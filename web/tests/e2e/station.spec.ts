import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

// Needs the built catalogue in web/public/catalogue (python -m pipeline catalogue --out web/public/catalogue).
const has = (p: string) => existsSync(fileURLToPath(new URL(`../../public/${p}`, import.meta.url)));
test.skip(!has("catalogue/stations.json"), "catalogue missing");

test("the New York City page", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const res = await page.goto("/us/new-york/new-york-city");
  expect(res?.status()).toBe(200);
  await expect(page).toHaveTitle("New York City tide times and weather · 3Dweather");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("New York City");
  await expect(page.locator(".st-crumbs")).toHaveText(/United States\s*\/\s*New York/);
  await expect(page.locator(".st-place")).toContainText("America/New_York");
  await expect(page.getByRole("link", { name: "Waves on the globe" })).toHaveAttribute("href", "/wave-map#40.71,-74.01,6.0");
  await expect(page.getByRole("link", { name: "United States weather map" })).toHaveAttribute("href", "/weather-map/united-states");
  const near = page.locator(".st-near a");
  await expect(near).toHaveCount(8);
  const href = await near.first().getAttribute("href");
  await near.first().click();
  await expect(page).toHaveURL(new RegExp(`${href}$`));
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText("New York City");
  expect(errors).toEqual([]);
});

test("a NOAA gauge page", async ({ page }) => {
  await page.goto("/us/hawaii/port-allen-hanapepe-bay");
  await expect(page.locator(".st-lede")).toHaveText("NOAA tide gauge 1611347 in Hawaii, United States.");
});

test("a station page fits a 320 px phone", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto("/us/new-york/new-york-city");
  const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(sw).toBeLessThanOrEqual(cw);
});

// Phase 9: pages built with daily station data (python -m pipeline station-data --out web/station-data).
const hasData = (p: string) => existsSync(fileURLToPath(new URL(`../../station-data/${p}.json`, import.meta.url)));

test.describe("station data", () => {
  test.skip(!hasData("us/new-york/new-york-city"), "station data missing");

  test("New York City shows today's tides, the month and its donor", async ({ page }) => {
    await page.goto("/us/new-york/new-york-city");
    const rows = page.locator(".st-month tbody tr");
    const n = await rows.count();
    expect(n).toBeGreaterThanOrEqual(28);
    expect(n).toBeLessThanOrEqual(31);
    await expect(page.locator(".st-month tbody tr.today")).toHaveCount(1);
    expect(await page.locator(".st-turns li").count()).toBeGreaterThanOrEqual(3);
    await expect(page.locator(".st-source")).toContainText("taken from");
    await expect(page.locator(".st-source")).toContainText("not NOAA's official predictions");
    await expect(page.locator(".st-sky")).toContainText("Sunrise");
  });

  test("the chart is drawn, a picked day redraws it and the unit switch changes heights", async ({ page }) => {
    await page.goto("/us/new-york/new-york-city");
    const curve = page.locator("svg[data-chart] path[data-curve]");
    await expect(curve).toHaveCount(1);
    const before = await curve.getAttribute("d");
    expect(before!.split("L").length).toBeGreaterThan(100);
    await expect(page.locator("svg[data-chart] [data-now]")).toHaveCount(1);
    const other = page.locator(".st-month tbody tr:not(.today) button[data-pick]").first();
    const label = (await other.textContent())!;
    await other.click();
    await expect(page.locator("[data-day-label]")).toHaveText(label);
    await expect.poll(() => curve.getAttribute("d")).not.toBe(before);
    await expect(page.locator("svg[data-chart] [data-now]")).toHaveCount(0);
    await expect(page.locator(".st-turns li span").first()).toContainText(" m");
    await page.locator("button[data-unit=ft]").click();
    await expect(page.locator(".st-turns li span").first()).toContainText(" ft");
    await expect(page.locator(".st-month tbody span[data-h]").first()).toContainText(" ft");
    await page.reload();
    await expect(page.locator(".st-turns li span").first()).toContainText(" ft"); // remembered
  });

  test("sun and moon follow the picked day", async ({ page }) => {
    await page.goto("/us/new-york/new-york-city");
    const row = page.locator(".st-month tbody tr:not(.today)").first();
    const sun = (await row.locator("td").nth(1).textContent())!.trim(); // "06:41–16:36"
    await row.locator("button[data-pick]").click();
    await expect(page.locator(".st-sky [data-sky=sunrise]")).toHaveText(sun.split("–")[0]);
    await expect(page.locator(".st-sky [data-sky-day]")).toHaveText((await row.locator("button").textContent())!);
  });

  test("the weather strip is a table of the station's forecast", async ({ page }) => {
    const start = new Date(Date.now() - 3600000);
    start.setUTCMinutes(0, 0, 0);
    const iso = start.toISOString().slice(0, 16) + "Z";
    await page.route("**/wx/latest.json", (r) => r.fulfill({ json: { run: iso, dir: "test" } }));
    await page.route("**/wx/test/stations/us/new-york.json", (r) => r.fulfill({ json: {
      v: 1, run: iso, start: iso, step_h: 3, n: 3, fields: ["t", "ws", "wd"], scale: { t: 10, ws: 10, wd: 1 },
      stations: { gNYC: { t: [101, 112, 123], ws: [50, 60, 70], wd: [0, 90, 180] } },
    } }));
    const id = await (await page.request.get("/us/new-york/new-york-city")).text();
    const sid = /data-station="([^"]+)"/.exec(id)![1];
    if (sid !== "gNYC") {
      await page.unroute("**/wx/test/stations/us/new-york.json");
      await page.route("**/wx/test/stations/us/new-york.json", (r) => r.fulfill({ json: {
        v: 1, run: iso, start: iso, step_h: 3, n: 3, fields: ["t", "ws", "wd"], scale: { t: 10, ws: 10, wd: 1 },
        stations: { [sid]: { t: [101, 112, 123], ws: [50, 60, 70], wd: [0, 90, 180] } },
      } }));
    }
    await page.goto("/us/new-york/new-york-city");
    const table = page.locator(".st-weather table.st-wx");
    await expect(table).toBeVisible();
    expect(await table.evaluate((t) => getComputedStyle(t).display)).toBe("table");
    await expect(table.locator("tbody tr").first()).toContainText("Air °C");
    expect(await table.locator("thead th").count()).toBeGreaterThanOrEqual(3);
  });

  test("after the embedded month ends, today comes from the tide table", async ({ page }) => {
    const html = await (await page.request.get("/us/new-york/new-york-city")).text();
    const data = JSON.parse(/<script type="application\/json" id="st-data">([\s\S]*?)<\/script>/.exec(html)![1]);
    const last = data.days[data.days.length - 1].date as string;
    const next = new Date(Date.parse(`${last}T12:00:00Z`) + 86400000).toISOString().slice(0, 10);
    const from = Date.parse(`${data.days[0].date}T00:00:00Z`);
    const turns: [number, number, number][] = [];
    for (let k = 0; k < 2 * 31 * 4; k++) turns.push([Math.round(k * 372.5), k % 2 ? -80 : 90, k % 2 ? 0 : 1]);
    await page.route(`**/tides/${data.path}.json`, (r) => r.fulfill({ json: {
      v: 1, id: data.id, source: "test", donor: null, datum: "MSL", from: new Date(from).toISOString().replace(".000", ""),
      to: new Date(from + 62 * 86400000).toISOString().replace(".000", ""), turns } }));
    await page.clock.setFixedTime(new Date(`${next}T17:00:00Z`)); // midday in New York
    await page.goto("/us/new-york/new-york-city");
    await expect(page.locator("[data-day-label]")).toHaveText(new Intl.DateTimeFormat("en-GB", {
      weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${next}T12:00:00Z`)));
    expect(await page.locator(".st-turns li").count()).toBeGreaterThanOrEqual(3);
    await expect(page.locator("svg[data-chart] [data-now]")).toHaveCount(1);
    await expect(page.locator(".st-month tbody tr.today")).toHaveCount(0);
  });

  test("a place without tides says so", async ({ page }) => {
    test.skip(!hasData("us/north-carolina/jacksonville"), "no-tide station data missing");
    await page.goto("/us/north-carolina/jacksonville");
    await expect(page.locator(".st-none")).toContainText("No tide predictions here");
    await expect(page.locator(".st-turns")).toHaveCount(0);
    await expect(page.locator(".st-sky")).toContainText("Sunrise");
  });
});
