// Build-time browse data: countries and regions (countries.json), popularity ranks (search.json)
// and the station tree behind the home, country and region pages.
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { DEFAULT_CATALOGUE, type StationRecord } from "./catalogue";

export type Region = { slug: string; name: string; count: number };
export type Country = { cc: string; name: string; continent: string; count: number; regions: Region[] };
export type RegionNode = Region & { stations: StationRecord[] };
export type CountryNode = Omit<Country, "regions"> & { regions: RegionNode[] };

export const CONTINENTS: Record<string, string> = {
  AF: "Africa", AN: "Antarctica", AS: "Asia", EU: "Europe", NA: "North America", OC: "Oceania", SA: "South America",
};

/** The folder holding the catalogue files (next to CATALOGUE_FILE). */
export function catalogueDir(): string {
  return dirname(process.env.CATALOGUE_FILE || DEFAULT_CATALOGUE);
}

function readJson<T>(file: string): T | null {
  if (!existsSync(file)) return null;
  return JSON.parse(readFileSync(file, "utf-8")) as T;
}

export function loadCountries(dir: string = catalogueDir()): Country[] {
  return readJson<Country[]>(join(dir, "countries.json")) ?? [];
}

export function loadRanks(dir: string = catalogueDir()): Map<string, number> {
  const f = readJson<{ fields: string[]; rows: (string | number)[][] }>(join(dir, "search.json"));
  const out = new Map<string, number>();
  if (!f) return out;
  const p = f.fields.indexOf("path"), r = f.fields.indexOf("rank");
  for (const row of f.rows) out.set(String(row[p]), Number(row[r]) || 0);
  return out;
}

export function continentOf(countries: Country[], cc: string): string {
  const c = countries.find((x) => x.cc === cc);
  return (c && CONTINENTS[c.continent]) || "Other";
}

const byName = (a: StationRecord, b: StationRecord) => a.name.localeCompare(b.name, "en");

/** Countries in countries.json order, each region holding its stations sorted by name. */
export function browseTree(stations: StationRecord[], countries: Country[], _ranks: Map<string, number>): CountryNode[] {
  const groups = new Map<string, Map<string, StationRecord[]>>();
  for (const s of stations) {
    const regions = groups.get(s.country_code) ?? new Map<string, StationRecord[]>();
    groups.set(s.country_code, regions);
    regions.set(s.region_slug, [...(regions.get(s.region_slug) ?? []), s]);
  }
  const out: CountryNode[] = [];
  for (const c of countries) {
    const regions = groups.get(c.cc);
    if (!regions) continue;
    out.push({
      ...c,
      regions: c.regions.filter((r) => regions.has(r.slug)).map((r) => ({ ...r, stations: regions.get(r.slug)!.sort(byName) })),
    });
  }
  return out;
}

/** Most visited first: rank (population) descending, then gauges, then name. */
export function popular(list: StationRecord[], ranks: Map<string, number>, n: number): StationRecord[] {
  return [...list].sort((a, b) => (ranks.get(b.path) ?? 0) - (ranks.get(a.path) ?? 0)
    || Number(b.type === "gauge") - Number(a.type === "gauge") || byName(a, b)).slice(0, n);
}
