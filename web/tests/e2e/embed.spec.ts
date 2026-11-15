import { expect, test, type Page } from "@playwright/test";

/** A synthetic 2-month table for one station, served in place of tides/{path}.json. */
async function routeTable(page: Page, path: string, extra: object = { name: "Test Harbour", tz: "America/New_York" }) {
  const from = Date.UTC(new Date().getUTCFullYear(), new Date().getUTCMonth() - 1, 1);
  const turns: [number, number, number][] = [];
  for (let k = 0; k < 3 * 31 * 4; k++) turns.push([Math.round(k * 372.5), k % 2 ? -80 : 90, k % 2 ? 0 : 1]);
  await page.route(`**/tides/${path}.json`, (r) => r.fulfill({ json: {
    v: 1, id: "t1", ...extra, source: "test", donor: null, datum: "MSL",
    from: new Date(from).toISOString().replace(".000", ""), to: new Date(from + 93 * 86400000).toISOString().replace(".000", ""), turns,
  } }));
}

test("the widget shows the place, its tides and a chart", async ({ page }) => {
  await routeTable(page, "us/new-york/test-harbour");
  await page.goto("/embed/tide?station=us/new-york/test-harbour&days=2&unit=ft&theme=light");
  await expect(page.locator(".w-name a")).toHaveText("Test Harbour");
  await expect(page.locator(".w-name a")).toHaveAttribute("href", /\/us\/new-york\/test-harbour$/);
  await expect(page.locator(".w-day")).toHaveCount(2);
  expect(await page.locator(".w-day").first().locator("li").count()).toBeGreaterThanOrEqual(3);
  await expect(page.locator(".w-day li").first()).toContainText("ft");
  await expect(page.locator("svg.w-chart path.curve")).toHaveCount(1);
  await expect(page.locator("svg.w-chart .now")).toHaveCount(1);
  await expect(page.locator("body")).toHaveClass(/light/);
  await expect(page.locator(".w-zone")).toContainText("America/New_York");
  await expect(page.locator(".w-credit")).toContainText("not for navigation");
});

test("a bad station shows a message and fetches nothing", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (r) => { if (r.url().includes("/tides/")) asked.push(r.url()); });
  await page.goto("/embed/tide?station=../../etc/passwd");
  await expect(page.locator(".w-msg")).toContainText("Choose a place");
  expect(asked).toEqual([]);
});

test("a missing table says so", async ({ page }) => {
  await page.route("**/tides/us/new-york/nowhere.json", (r) => r.fulfill({ status: 404, body: "" }));
  await page.goto("/embed/tide?station=us/new-york/nowhere");
  await expect(page.locator(".w-msg")).toContainText("No tide table");
});

test("the widget fits 280 px", async ({ page }) => {
  await routeTable(page, "us/new-york/test-harbour");
  await page.setViewportSize({ width: 280, height: 500 });
  await page.goto("/embed/tide?station=us/new-york/test-harbour&days=3");
  await expect(page.locator(".w-day")).toHaveCount(3);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(280);
});

test.describe("builder", () => {
  test("choosing a place and options updates the preview and the code", async ({ page }) => {
    await page.route("**/tides/**", (r) => r.fulfill({ status: 404, body: "" })); // the preview's content is not under test
    await page.goto("/embed");
    await page.locator("[data-embed-search]").fill("New York City");
    const option = page.getByRole("button", { name: /^New York City/ }).first();
    test.skip(!(await option.waitFor({ timeout: 10000 }).then(() => true, () => false)), "catalogue missing");
    await option.click();
    const frame = page.locator("iframe[data-embed-preview]");
    await expect(frame).toHaveAttribute("src", /station=us%2Fnew-york%2Fnew-york-city/);
    const code = page.locator("textarea[data-embed-code]");
    await expect(code).toHaveValue(/<iframe src="[^"]*station=us%2Fnew-york%2Fnew-york-city/);
    await page.locator("select[data-opt=unit]").selectOption("ft");
    await page.locator("select[data-opt=days]").selectOption("3");
    await expect(frame).toHaveAttribute("src", /unit=ft&theme=dark&days=3/);
    await expect(code).toHaveValue(/unit=ft&amp;theme=dark&amp;days=3/);
    await expect(code).toHaveValue(/height="460"/);
  });

  test("a station page link preselects its place", async ({ page }) => {
    await page.route("**/tides/**", (r) => r.fulfill({ status: 404, body: "" }));
    await page.goto("/embed?station=us/new-york/new-york-city");
    await expect(page.locator("iframe[data-embed-preview]")).toHaveAttribute("src", /station=us%2Fnew-york%2Fnew-york-city/);
    await expect(page.locator("[data-embed-chosen]")).toContainText("New York City");
  });
});

test("station pages with tides link to the builder for their place", async ({ page }) => {
  const res = await page.request.get("/us/new-york/new-york-city");
  test.skip(!res.ok() || !(await res.text()).includes('id="st-data"'), "station data missing");
  await page.goto("/us/new-york/new-york-city");
  await expect(page.locator("[data-embed-link]")).toHaveAttribute("href", "/embed?station=us/new-york/new-york-city");
});
