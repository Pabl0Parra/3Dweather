import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "vitest";
import { loadStations, makeIndex, nearbyStations, regionFor, type StationRecord } from "./catalogue";

const rec = (id: string, name: string, lat: number, lon: number, extra: Partial<StationRecord> = {}): StationRecord => ({
  id, slug: name.toLowerCase().replace(/\W+/g, "-"), name, country_code: "US", region_name: "New York",
  region_slug: "new-york", county: null, island: null, latitude: lat, longitude: lon, timezone: "America/New_York",
  type: "place", has_tides: true, has_current_station: false, reference_station: null, timing_offset_minutes: null,
  path: `us/new-york/${name.toLowerCase().replace(/\W+/g, "-")}`, ...extra,
});

const ALL = [
  rec("g1", "New York City", 40.7143, -74.006),
  rec("n1", "The Battery", 40.7006, -74.0142, { type: "gauge" }),
  rec("g2", "Hoboken", 40.744, -74.0324),
  rec("g3", "Yonkers", 40.9312, -73.8988),
  rec("g4", "Montauk", 41.0359, -71.9545),
  rec("g5", "Galway", 53.27, -9.05, { country_code: "IE" }),
  rec("g6", "Suva", -18.14, 178.44),
  rec("g7", "Apia", -13.83, -171.77),
];

test("a missing catalogue file means no station pages", () => {
  expect(loadStations(join(tmpdir(), "no-such-dir-3dweather", "stations.json"))).toEqual([]);
});

test("loads a catalogue file", () => {
  const dir = mkdtempSync(join(tmpdir(), "cat-"));
  const f = join(dir, "stations.json");
  writeFileSync(f, JSON.stringify(ALL), "utf-8");
  expect(loadStations(f)).toHaveLength(ALL.length);
});

test("nearby stations exclude the station itself and come nearest first", () => {
  const idx = makeIndex(ALL);
  const near = nearbyStations(idx, ALL[0], 3);
  expect(near.map((n) => n.name)).toEqual(["The Battery", "Hoboken", "Yonkers"]);
  expect(near[0].km).toBeLessThan(2);
  expect(nearbyStations(idx, ALL[0], 50)).toHaveLength(ALL.length - 1); // asks for more than exist
});

test("nearby search crosses the antimeridian", () => {
  const near = nearbyStations(makeIndex(ALL), ALL[6], 1);
  expect(near[0].name).toBe("Apia");
});

test("the smallest regional map containing the station", () => {
  expect(regionFor(ALL[0])?.slug).toBe("united-states");
  expect(regionFor(ALL[5])?.slug).toBe("ireland"); // Galway sits in Ireland, UK and Europe; Ireland is smallest
  expect(regionFor(ALL[6])).toBeNull();
});
