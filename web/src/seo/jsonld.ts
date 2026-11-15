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
