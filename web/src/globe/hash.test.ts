import { expect, test } from "vitest";
import { formatHash, parseHash } from "./hash";

test("parse and format round trip", () => {
  expect(parseHash("#44.5,9.5,2.7")).toEqual({ lat0: 44.5, lon0: 9.5, zoom: 2.7 });
  expect(formatHash({ lat0: 44.5, lon0: 9.5, zoom: 2.7 })).toBe("#44.50,9.50,2.7");
});

test("bad hashes", () => {
  expect(parseHash("#abc")).toBeNull();
  expect(parseHash("")).toBeNull();
  expect(parseHash("#1,2")).toBeNull();
  expect(parseHash("#120,500,99")).toEqual({ lat0: 85, lon0: 140, zoom: 16 });
});
