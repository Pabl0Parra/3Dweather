import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const hasCatalogue = existsSync(fileURLToPath(new URL("../../public/catalogue/countries.json", import.meta.url)));
const hasData = existsSync(fileURLToPath(new URL("../../station-data/us/new-york/new-york-city.json", import.meta.url)));

test("robots.txt points at the sitemap index, which lists the sitemap files", async ({ request }) => {
  const robots = await (await request.get("/robots.txt")).text();
  expect(robots).toMatch(/Sitemap: .*\/sitemap\.xml/);
  const index = await (await request.get("/sitemap.xml")).text();
  expect(index).toContain("<sitemapindex");
  expect(index).toContain("/sitemaps/pages.xml");
  const pages = await (await request.get("/sitemaps/pages.xml")).text();
  expect(pages).toMatch(/<loc>[^<]*\/wave-map<\/loc>/);
  test.skip(!hasCatalogue, "catalogue missing");
  expect(index).toContain("/sitemaps/stations-1.xml");
  const st = await (await request.get("/sitemaps/stations-1.xml")).text();
  expect(st).toContain("/us/new-york/new-york-city</loc>");
});

test("pages carry a canonical link and valid JSON-LD", async ({ page }) => {
  test.skip(!hasCatalogue || !hasData, "catalogue or station data missing");
  for (const [path, types] of [["/", ["WebSite"]], ["/us/new-york", ["BreadcrumbList"]],
    ["/us/new-york/new-york-city", ["BreadcrumbList", "FAQPage"]]] as [string, string[]][]) {
    await page.goto(path);
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", new RegExp(`${path === "/" ? "/$" : path + "$"}`));
    const blocks = await page.locator('script[type="application/ld+json"]').allTextContents();
    expect(blocks.map((b) => JSON.parse(b)["@type"])).toEqual(types);
  }
  await expect(page.locator(".st-faq summary").first()).toContainText("New York City");
});
