import { siteUrl } from "../seo/sitemap";

export function GET(): Response {
  return new Response(`User-agent: *\nAllow: /\n\nSitemap: ${siteUrl()}/sitemap.xml\n`, { headers: { "Content-Type": "text/plain" } });
}
