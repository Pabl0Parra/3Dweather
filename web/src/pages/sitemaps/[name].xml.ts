import type { APIContext } from "astro";
import { siteUrl, urlset } from "../../seo/sitemap";
import { pagePaths, placePaths, sitemapNames, stationPathChunks } from "../../seo/paths";

export function getStaticPaths() {
  return sitemapNames().map((name) => ({ params: { name } }));
}

export function GET({ params }: APIContext): Response {
  const name = params.name!;
  const paths = name === "pages" ? pagePaths() : name === "places" ? placePaths()
    : stationPathChunks()[Number(name.replace("stations-", "")) - 1] ?? [];
  return new Response(urlset(siteUrl(), paths), { headers: { "Content-Type": "application/xml" } });
}
