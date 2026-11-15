// Build-time access to the station catalogue (stations.json from `python -m pipeline catalogue`).
import { existsSync, readFileSync } from "node:fs";
import { km } from "../search/catalogue";
import { REGIONS, type RegionInfo } from "../region/regions";

export type StationRecord = {
  id: string; slug: string; name: string; country_code: string; region_name: string; region_slug: string;
  county: string | null; island: string | null; latitude: number; longitude: number; timezone: string;
  type: "place" | "gauge"; has_tides: boolean; has_current_station: boolean;
  reference_station: { slug: string; name: string; path: string } | null;
  timing_offset_minutes: number | null; path: string;
};

export const DEFAULT_CATALOGUE = "public/catalogue/stations.json";

/** The catalogue, or none when the file is missing (CI and forks build without it). */
export function loadStations(file: string = process.env.CATALOGUE_FILE || DEFAULT_CATALOGUE): StationRecord[] {
  if (!existsSync(file)) return [];
  return JSON.parse(readFileSync(file, "utf-8")) as StationRecord[];
}

export type StationIndex = { cells: Map<string, StationRecord[]> };

const cellKey = (i: number, j: number) => `${i},${((j % 360) + 360) % 360}`;

/** One-degree buckets, so 24,000 pages can each find their neighbours quickly. */
export function makeIndex(all: StationRecord[]): StationIndex {
  const cells = new Map<string, StationRecord[]>();
  for (const s of all) {
    const k = cellKey(Math.floor(s.latitude), Math.floor(s.longitude));
    const list = cells.get(k);
    if (list) list.push(s);
    else cells.set(k, [s]);
  }
  return { cells };
}

/** The `n` nearest other stations, nearest first, searching outward ring by ring. */
export function nearbyStations(idx: StationIndex, s: StationRecord, n = 8): (StationRecord & { km: number })[] {
  const i0 = Math.floor(s.latitude);
  const j0 = Math.floor(s.longitude);
  const seen = new Set<string>();
  const found: (StationRecord & { km: number })[] = [];
  for (let r = 0; r <= 180; r++) {
    for (let i = i0 - r; i <= i0 + r; i++) {
      if (i < -90 || i > 89) continue;
      for (let j = j0 - r; j <= j0 + r; j++) {
        if (Math.abs(i - i0) !== r && Math.abs(j - j0) !== r) continue; // ring cells only
        const k = cellKey(i, j);
        if (seen.has(k)) continue;
        seen.add(k);
        for (const o of idx.cells.get(k) ?? []) {
          if (o.id !== s.id) found.push({ ...o, km: km(s.latitude, s.longitude, o.latitude, o.longitude) });
        }
      }
    }
    if (found.length >= n) {
      found.sort((a, b) => a.km - b.km);
      // Every unvisited cell is at least r whole cells away; at this latitude a cell is at least this wide.
      const cos = Math.cos((Math.min(89, Math.abs(s.latitude) + r + 1) * Math.PI) / 180);
      if (found[n - 1].km <= r * 111.2 * cos) break;
    }
  }
  return found.sort((a, b) => a.km - b.km).slice(0, n);
}

const area = (r: RegionInfo) => (r.bounds[2] - r.bounds[0]) * (r.bounds[3] - r.bounds[1]);

/** The smallest regional map whose extent contains the station, if any. */
export function regionFor(s: StationRecord): RegionInfo | null {
  const inside = REGIONS.filter((r) => {
    const [w, so, e, no] = r.bounds;
    return s.latitude >= so && s.latitude <= no && s.longitude >= w && s.longitude <= e;
  });
  return inside.sort((a, b) => area(a) - area(b))[0] ?? null;
}

export const DEFAULT_STATION_DATA = "station-data";

/** The daily data file for one station (python -m pipeline station-data), or null without one. */
export function loadStationData(path: string, dir: string = process.env.STATION_DATA_DIR || DEFAULT_STATION_DATA):
  import("../station/format").StationData | null {
  const file = `${dir}/${path}.json`;
  if (!existsSync(file)) return null;
  return JSON.parse(readFileSync(file, "utf-8"));
}
