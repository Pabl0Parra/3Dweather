// Sitemaps: an index pointing at a pages file, a places file (countries and regions) and station
// files of at most STATION_CHUNK URLs (the protocol allows 50,000 per file).

export const STATION_CHUNK = 40000;

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function stationChunks<T>(items: T[]): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += STATION_CHUNK) out.push(items.slice(i, i + STATION_CHUNK));
  return out;
}

export function urlset(site: string, paths: string[]): string {
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
    + paths.map((p) => `<url><loc>${esc(site + p)}</loc></url>`).join("\n") + "\n</urlset>\n";
}

export function sitemapIndex(site: string, names: string[]): string {
  return `<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
    + names.map((n) => `<sitemap><loc>${esc(`${site}/sitemaps/${n}.xml`)}</loc></sitemap>`).join("\n") + "\n</sitemapindex>\n";
}

export function siteUrl(): string {
  return (process.env.SITE_URL || "https://example.invalid").replace(/\/$/, "");
}
