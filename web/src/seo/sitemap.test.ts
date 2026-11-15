import { describe, expect, it } from "vitest";
import { STATION_CHUNK, sitemapIndex, stationChunks, urlset } from "./sitemap";

describe("sitemaps", () => {
  it("splits station URLs into files under the 50,000 limit", () => {
    const paths = Array.from({ length: STATION_CHUNK * 2 + 5 }, (_, k) => `x/y/s${k}`);
    const chunks = stationChunks(paths);
    expect(chunks.map((c) => c.length)).toEqual([STATION_CHUNK, STATION_CHUNK, 5]);
    expect(STATION_CHUNK).toBeLessThanOrEqual(50000);
  });

  it("writes a urlset with escaped absolute URLs", () => {
    const xml = urlset("https://s.test", ["/", "/a&b"]);
    expect(xml).toContain('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">');
    expect(xml).toContain("<loc>https://s.test/</loc>");
    expect(xml).toContain("<loc>https://s.test/a&amp;b</loc>");
  });

  it("indexes the sitemap files", () => {
    const xml = sitemapIndex("https://s.test", ["pages", "stations-1"]);
    expect(xml).toContain("<sitemapindex");
    expect(xml).toContain("<loc>https://s.test/sitemaps/stations-1.xml</loc>");
  });
});
