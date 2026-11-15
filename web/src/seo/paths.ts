// Every public URL path, grouped as the sitemaps list them.
import { LAYER_IDS, LAYERS } from "../globe/layers";
import { REGIONS } from "../region/regions";
import { browseTree, loadCountries, loadRanks } from "../stations/browse";
import { loadStations } from "../stations/catalogue";
import { stationChunks } from "./sitemap";

export const STATIC_PATHS = ["/", "/stations", "/guides", "/what-is-a-tide", "/tidal-coefficient", "/solunar-times",
  "/about", "/privacy", "/terms", "/embed"];

export function pagePaths(): string[] {
  return [...STATIC_PATHS, ...LAYER_IDS.map((id) => LAYERS[id].path),
    ...REGIONS.flatMap((r) => [`/weather-map/${r.slug}`, `/wind-map/${r.slug}`])];
}

export function placePaths(): string[] {
  return browseTree(loadStations(), loadCountries(), loadRanks()).flatMap((c) => {
    const cc = `/${c.cc.toLowerCase()}`;
    return [cc, ...c.regions.map((r) => `${cc}/${r.slug}`)];
  });
}

export function stationPathChunks(): string[][] {
  return stationChunks(loadStations().map((s) => `/${s.path}`));
}

/** Sitemap file names, in index order. */
export function sitemapNames(): string[] {
  const places = placePaths().length ? ["places"] : [];
  return ["pages", ...places, ...stationPathChunks().map((_, k) => `stations-${k + 1}`)];
}
