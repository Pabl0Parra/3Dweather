import { expect, test } from "vitest";
import { fold, inBounds, makeCatalogue, nearest, search, type SearchFile } from "./catalogue";

const FILE: SearchFile = {
  v: 1,
  fields: ["id", "name", "cc", "region", "lat", "lon", "type", "path", "rank"],
  rows: [
    ["g1", "New York City", "US", "New York", 40.7143, -74.006, 1, "us/new-york/new-york-city", 6],
    ["n8518750", "The Battery", "US", "New York", 40.7006, -74.0142, 0, "us/new-york/the-battery", 9],
    ["g2", "West New York", "US", "New Jersey", 40.7879, -74.0143, 1, "us/new-jersey/west-new-york", 4],
    ["g3", "Newport", "US", "Rhode Island", 41.4901, -71.3128, 1, "us/rhode-island/newport", 4],
    ["g4", "São Paulo de Olivença", "BR", "Amazonas", -3.38, -68.87, 1, "br/amazonas/sao-paulo-de-olivenca", 4],
    ["g5", "St. John's", "CA", "Newfoundland and Labrador", 47.5649, -52.7093, 1, "ca/newfoundland-and-labrador/st-john-s", 5],
    ["g6", "Portland", "US", "Maine", 43.6615, -70.2553, 1, "us/maine/portland", 4],
    ["g7", "Portland", "US", "Oregon", 45.5234, -122.6762, 1, "us/oregon/portland", 6],
    ["g8", "Suva", "FJ", "Central", -18.1416, 178.4415, 1, "fj/central/suva", 5],
    ["g9", "Apia", "WS", "Tuamasaga", -13.8333, -171.7667, 1, "ws/tuamasaga/apia", 4],
  ],
};
const C = makeCatalogue(FILE);
const names = (es: { name: string }[]) => es.map((e) => e.name);

test("fold strips accents, case and punctuation", () => {
  expect(fold("São Paulo")).toBe("sao paulo");
  expect(fold("St. John's")).toBe("st johns"); // apostrophes join, other punctuation splits
  expect(fold("O’Brien")).toBe("obrien");
  expect(fold("  NEW   York ")).toBe("new york");
});

test("rows become entries", () => {
  expect(C.entries).toHaveLength(10);
  expect(C.entries[1]).toMatchObject({ id: "n8518750", type: "gauge", path: "us/new-york/the-battery", rank: 9 }); // the fixture sets its own ranks
});

test("exact, then name prefix, then word prefix, then substring", () => {
  expect(names(search(C, "new york"))).toEqual(["New York City", "West New York"]);
  expect(names(search(C, "new"))).toEqual(["New York City", "Newport", "West New York"]);
  expect(names(search(C, "battery"))).toEqual(["The Battery"]);
  expect(names(search(C, "port"))[0]).toBe("Portland"); // prefix before Newport's substring
  expect(names(search(C, "port")).at(-1)).toBe("Newport");
});

test("ties go to the higher rank", () => {
  expect(search(C, "portland").map((e) => e.region)).toEqual(["Oregon", "Maine"]);
});

test("words can match the region", () => {
  expect(search(C, "portland maine").map((e) => e.path)).toEqual(["us/maine/portland"]);
});

test("accents and punctuation in the query", () => {
  expect(names(search(C, "sao paulo"))).toEqual(["São Paulo de Olivença"]);
  expect(names(search(C, "São"))).toEqual(["São Paulo de Olivença"]);
  expect(names(search(C, "st. john's"))).toEqual(["St. John's"]);
  expect(names(search(C, "st johns"))).toEqual(["St. John's"]);
  expect(names(search(C, "st john"))).toEqual(["St. John's"]);
});

test("short or empty queries give nothing; limit applies", () => {
  expect(search(C, "")).toEqual([]);
  expect(search(C, "n")).toEqual([]);
  expect(search(C, " . ")).toEqual([]);
  expect(search(C, "new", 2)).toHaveLength(2);
});

test("nearest orders by great-circle distance", () => {
  const n = nearest(C, 40.7, -74.0, 3);
  expect(names(n)).toEqual(["The Battery", "New York City", "West New York"]);
  expect(n[0].km).toBeLessThan(2);
  expect(n[2].km).toBeGreaterThan(n[1].km);
});

test("in bounds, including across the antimeridian", () => {
  expect(names(inBounds(C, -75, 40, -73, 41, 10)).sort()).toEqual(["New York City", "The Battery", "West New York"]);
  expect(names(inBounds(C, 170, -25, -170, -10, 10)).sort()).toEqual(["Apia", "Suva"]);
  expect(inBounds(C, -75, 40, -73, 41, 1)).toHaveLength(1);
});
