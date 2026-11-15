import { sitemapIndex, siteUrl } from "../seo/sitemap";
import { sitemapNames } from "../seo/paths";

export function GET(): Response {
  return new Response(sitemapIndex(siteUrl(), sitemapNames()), { headers: { "Content-Type": "application/xml" } });
}
