// Embed widget options: parsed from the iframe's query string, and turned back into a URL and an
// <iframe> snippet by the builder.

export type EmbedOptions = { station: string | null; unit: "m" | "ft"; theme: "dark" | "light"; days: 1 | 2 | 3 };

const PATH = /^[a-z0-9-]+(\/[a-z0-9-]+){2}$/; // country/region/station, as in the catalogue

export function parseParams(search: string): EmbedOptions {
  const q = new URLSearchParams(search);
  const station = q.get("station");
  const days = Math.max(1, Math.min(3, Math.round(Number(q.get("days")) || 1))) as 1 | 2 | 3;
  return {
    station: station && PATH.test(station) ? station : null,
    unit: q.get("unit") === "ft" ? "ft" : "m",
    theme: q.get("theme") === "light" ? "light" : "dark",
    days,
  };
}

export function embedUrl(site: string, o: EmbedOptions): string {
  const q = new URLSearchParams({ station: o.station ?? "", unit: o.unit, theme: o.theme, days: String(o.days) });
  return `${site}/embed/tide?${q}`;
}

/** Height that fits the widget without scrolling (title, one block per day, chart, credit). */
export function embedHeight(days: number): number {
  return 250 + 70 * days;
}

const attr = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function iframeSnippet(site: string, o: EmbedOptions, name: string): string {
  return `<iframe src="${attr(embedUrl(site, o))}" title="${attr(`Tide times for ${name}`)}" width="100%" height="${embedHeight(o.days)}"`
    + ` style="max-width:420px;border:0;border-radius:12px" loading="lazy"></iframe>`;
}
