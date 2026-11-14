import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

// Needs the built catalogue in web/public/catalogue (python -m pipeline catalogue --out web/public/catalogue).
const has = (p: string) => existsSync(fileURLToPath(new URL(`../../public/${p}`, import.meta.url)));
test.skip(!has("catalogue/search.json"), "catalogue missing");

test("typing finds New York City and Enter goes to its page", async ({ page }) => {
  await page.goto("/weather-map/europe");
  await page.getByRole("button", { name: "Search" }).click();
  const box = page.getByRole("combobox", { name: /Search tide stations/ });
  await expect(box).toBeFocused();
  await box.fill("new york");
  const first = page.locator("#station-results [role=option]").first();
  await expect(first).toContainText("New York City");
  await expect(first.locator("a")).toHaveAttribute("href", "/us/new-york/new-york-city");
  await expect(box).toHaveAttribute("aria-expanded", "true");
  await box.press("ArrowDown");
  await expect(first).toHaveAttribute("aria-selected", "true");
  await expect(box).toHaveAttribute("aria-activedescendant", "station-opt-0");
  await box.press("Enter");
  await expect(page).toHaveURL(/\/us\/new-york\/new-york-city$/);
});

test("accents, no matches and Escape", async ({ page }) => {
  await page.goto("/wave-map");
  await page.getByRole("button", { name: "Search" }).click();
  const box = page.getByRole("combobox");
  await box.fill("sao paulo");
  await expect(page.locator("#station-results [role=option]").first()).toContainText(/São Paulo/);
  await box.fill("zzqqxx");
  await expect(page.locator(".search-status")).toHaveText("No matching stations.");
  await box.fill("n");
  await expect(page.locator("#station-results [role=option]")).toHaveCount(0);
  await box.press("Escape");
  await expect(page.locator("#search-panel")).toBeHidden();
  await expect(page.getByRole("button", { name: "Search" })).toBeFocused();
});

test("search fits a 320 px phone", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto("/wave-map");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("combobox").fill("port");
  await expect(page.locator("#station-results [role=option]").first()).toBeVisible();
  const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(sw).toBeLessThanOrEqual(cw);
  const box = (await page.locator("#search-panel").boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(320);
});

test("Enter right after typing opens the new query's result, not the old one", async ({ page }) => {
  await page.goto("/wave-map");
  await page.getByRole("button", { name: "Search" }).click();
  const box = page.getByRole("combobox");
  await box.fill("new york");
  await expect(page.locator("#station-results [role=option]").first()).toContainText("New York City");
  await box.fill("honolulu");
  await box.press("Enter"); // inside the 80 ms debounce
  await expect(page).toHaveURL(/\/us\/hawaii\/honolulu$/);
});
