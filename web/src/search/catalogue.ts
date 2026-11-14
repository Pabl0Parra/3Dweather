// The station catalogue's compact search file, searched in the browser (replaces a search API).

export type SearchFile = { v: 1; fields: string[]; rows: (string | number)[][] };

export type Entry = {
  id: string; name: string; cc: string; region: string; lat: number; lon: number;
  type: "gauge" | "place"; path: string; rank: number;
  /** Folded name, and folded "name region cc" for multi-word queries. */
  key: string; all: string;
};

export type Catalogue = { entries: Entry[] };

const CATALOGUE_BASE: string = import.meta.env.PUBLIC_CATALOGUE_BASE || "/catalogue";

/** Lower-case, accents removed, every run of non-alphanumerics a single space. */
export function fold(s: string): string {
  return s.normalize("NFD").replace(/\p{M}+/gu, "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}

export function makeCatalogue(f: SearchFile): Catalogue {
  const at = (n: string) => f.fields.indexOf(n);
  const [id, name, cc, region, lat, lon, type, path, rank] =
    ["id", "name", "cc", "region", "lat", "lon", "type", "path", "rank"].map(at);
  const entries = f.rows.map((r): Entry => {
    const nm = String(r[name]);
    const rg = String(r[region]);
    return {
      id: String(r[id]), name: nm, cc: String(r[cc]), region: rg, lat: Number(r[lat]), lon: Number(r[lon]),
      type: r[type] === 0 ? "gauge" : "place", path: String(r[path]), rank: Number(r[rank]),
      key: fold(nm), all: ` ${fold(`${nm} ${rg} ${r[cc]}`)}`,
    };
  });
  return { entries };
}

let loading: Promise<Catalogue> | null = null;

/** Fetched once per page, on first use. */
export function loadCatalogue(base = CATALOGUE_BASE): Promise<Catalogue> {
  loading ??= fetch(`${base}/search.json`).then((r) => {
    if (!r.ok) throw new Error(`catalogue: HTTP ${r.status}`);
    return r.json();
  }).then(makeCatalogue).catch((e) => { loading = null; throw e; });
  return loading;
}

/** 0 exact, 1 name prefix, 2 word prefix in the name, 3 inside the name, 4 every word matches name or region. */
function score(e: Entry, q: string, words: string[]): number {
  if (e.key === q) return 0;
  if (e.key.startsWith(q)) return 1;
  if (` ${e.key}`.includes(` ${q}`)) return 2;
  if (e.key.includes(q)) return 3;
  if (words.length > 1 && ` ${e.key}`.includes(` ${words[0]}`) && words.every((w) => e.all.includes(` ${w}`))) return 4;
  return -1;
}

export function search(c: Catalogue, query: string, limit = 8): Entry[] {
  const q = fold(query);
  if (q.length < 2) return [];
  const words = q.split(" ");
  const hits: [number, Entry][] = [];
  for (const e of c.entries) {
    const s = score(e, q, words);
    if (s >= 0) hits.push([s, e]);
  }
  hits.sort((a, b) => a[0] - b[0] || b[1].rank - a[1].rank || a[1].name.length - b[1].name.length
    || a[1].name.localeCompare(b[1].name));
  return hits.slice(0, limit).map((h) => h[1]);
}

const RAD = Math.PI / 180;

export function km(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const a = Math.sin(((lat2 - lat1) * RAD) / 2) ** 2
    + Math.cos(lat1 * RAD) * Math.cos(lat2 * RAD) * Math.sin(((lon2 - lon1) * RAD) / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(a)));
}

export function nearest(c: Catalogue, lat: number, lon: number, n: number): (Entry & { km: number })[] {
  return c.entries.map((e) => ({ ...e, km: km(lat, lon, e.lat, e.lon) }))
    .sort((a, b) => a.km - b.km).slice(0, n);
}

/** Stations inside a box, highest rank first; `west > east` means the box crosses ±180°. */
export function inBounds(c: Catalogue, west: number, south: number, east: number, north: number, limit: number): Entry[] {
  const inLon = west <= east ? (l: number) => l >= west && l <= east : (l: number) => l >= west || l <= east;
  return c.entries.filter((e) => e.lat >= south && e.lat <= north && inLon(e.lon))
    .sort((a, b) => b.rank - a.rank).slice(0, limit);
}
