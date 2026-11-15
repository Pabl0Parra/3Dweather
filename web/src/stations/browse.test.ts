import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { browseTree, continentOf, loadCountries, loadRanks, popular } from "./browse";
import type { StationRecord } from "./catalogue";

const st = (id: string, name: string, cc: string, region: string, type: "place" | "gauge" = "place") => ({
  id, name, slug: name.toLowerCase(), country_code: cc, region_name: region, region_slug: region.toLowerCase(),
  county: null, island: null, latitude: 0, longitude: 0, timezone: "UTC", type, has_tides: true,
  has_current_station: false, reference_station: null, timing_offset_minutes: null,
  path: `${cc.toLowerCase()}/${region.toLowerCase()}/${name.toLowerCase()}`,
}) as StationRecord;

const stations = [st("a", "Zeta", "US", "Maine"), st("b", "Alpha", "US", "Maine", "gauge"), st("c", "Beta", "FR", "Bretagne")];
const countries = [
  { cc: "US", name: "United States", continent: "NA", count: 2, regions: [{ slug: "maine", name: "Maine", count: 2 }] },
  { cc: "FR", name: "France", continent: "EU", count: 1, regions: [{ slug: "bretagne", name: "Bretagne", count: 1 }] },
];

describe("browse data", () => {
  it("groups stations by country and region, sorted by name", () => {
    const tree = browseTree(stations, countries, new Map());
    expect(tree.map((c) => c.cc)).toEqual(["US", "FR"]);
    expect(tree[0].regions[0].stations.map((s) => s.name)).toEqual(["Alpha", "Zeta"]);
    expect(tree[1].regions[0].stations.map((s) => s.name)).toEqual(["Beta"]);
  });

  it("orders popular places by rank, then gauges, then name", () => {
    const ranks = new Map([["us/maine/zeta", 7]]);
    expect(popular(stations.slice(0, 2), ranks, 2).map((s) => s.name)).toEqual(["Zeta", "Alpha"]);
    expect(popular(stations.slice(0, 2), new Map(), 2).map((s) => s.name)).toEqual(["Alpha", "Zeta"]);
  });

  it("reads countries and ranks, and goes without them", () => {
    const dir = mkdtempSync(join(tmpdir(), "browse-"));
    expect(loadCountries(dir)).toEqual([]);
    expect(loadRanks(dir).size).toBe(0);
    writeFileSync(join(dir, "countries.json"), JSON.stringify(countries));
    writeFileSync(join(dir, "search.json"), JSON.stringify({ v: 1, fields: ["id", "path", "rank"], rows: [["a", "us/maine/zeta", 5]] }));
    expect(loadCountries(dir)[1].name).toBe("France");
    expect(loadRanks(dir).get("us/maine/zeta")).toBe(5);
    expect(continentOf(countries, "FR")).toBe("Europe");
  });
});
