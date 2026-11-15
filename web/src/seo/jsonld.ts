// JSON-LD for search engines: breadcrumbs, the station FAQ, and safe embedding in <script>.

/** JSON safe inside <script type="application/ld+json">: no "<", ">", "&" or line separators. */
export function jsonScript(obj: unknown): string {
  return JSON.stringify(obj)
    .replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
}

/** schema.org BreadcrumbList from [name, path] pairs. */
export function breadcrumbs(site: string, items: [string, string][]): object {
  return {
    "@context": "https://schema.org", "@type": "BreadcrumbList",
    itemListElement: items.map(([name, path], k) => ({ "@type": "ListItem", position: k + 1, name, item: `${site}${path}` })),
  };
}

export type Faq = { q: string; a: string };

/** The questions on every station page, answered from the station's own facts (visible on the page too). */
export function stationFaq(name: string, tz: string, source: string | null, donor: string | null): Faq[] {
  const from = source == null
    ? `There are no tide predictions for ${name}: it is too far from the open sea in our tide model. Sun and moon times are still shown.`
    : `They are computed by 3Dweather from ${source}${donor ? `, taken from ${donor}` : ""}. Heights are above mean sea level.`;
  return [
    { q: `Where do the tide times for ${name} come from?`, a: from },
    { q: `What time zone are the times for ${name} in?`, a: `All times are local time at ${name} (${tz}), including daylight saving time.` },
    { q: "Are these tide times official?", a: "No. They are predictions of the astronomical tide, not NOAA's official predictions or any other agency's, and they leave out weather effects such as storm surge. Do not use them for navigation." },
    { q: `How often is the page for ${name} updated?`, a: "Tides, sun and moon are rebuilt every day; the weather forecast every six hours." },
  ];
}

export function faqJsonLd(faq: Faq[]): object {
  return {
    "@context": "https://schema.org", "@type": "FAQPage",
    mainEntity: faq.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
  };
}
