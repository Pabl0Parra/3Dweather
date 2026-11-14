import { expect, test } from "vitest";
import { decodeHeight } from "./codecs";
import { LandGrid } from "./field";
import { biggestWave, easeInOutCubic, FLY_MS, FLY_ZOOM, flyView } from "./fly";
import type { GlobeManifest } from "./manifest";
import { clampView } from "./view";

// Toy 4x2 grid: cell centres at lon -135, -45, 45, 135 and lat 45, -45.
const M = { w: 4, h: 2, west: -135, dlon: 90, north: 45, dlat: 90 } as GlobeManifest;

test("constants", () => {
  expect(FLY_MS).toBe(1400);
  expect(FLY_ZOOM).toBe(3.2);
});

test("finds the highest sea cell", () => {
  const px = new Uint8ClampedArray(4 * 2 * 4);
  const r = [250, 10, 240, 30, 5, 5, 5, 5]; // 250 sits on land
  r.forEach((v, i) => (px[i * 4] = v));
  const land = new LandGrid(Uint8Array.from([255, 0, 0, 0, 0, 0, 0, 0]), 4, 2); // cell (0,0) is land
  expect(biggestWave(px, M, land)).toEqual({ lat: 45, lon: 45, heightM: decodeHeight(240) });
});

test("flies the short way round", () => {
  const mid = flyView({ lat0: 0, lon0: 170, zoom: 1 }, { lat0: 0, lon0: -170, zoom: 1 }, 0.5);
  expect(Math.abs(Math.abs(mid.lon0) - 180)).toBeLessThan(1e-6);
});

test("ends exactly on target", () => {
  const A = { lat0: 10, lon0: 20, zoom: 1 }, B = { lat0: 44.28, lon0: -140.92, zoom: 3.2 };
  expect(flyView(A, B, 1)).toEqual(clampView(B));
  expect(flyView(A, B, 0)).toEqual(clampView(A));
});

test("zoom interpolates geometrically", () => {
  expect(flyView({ lat0: 0, lon0: 0, zoom: 1 }, { lat0: 0, lon0: 0, zoom: 4 }, 0.5).zoom).toBeCloseTo(2);
});

test("ease", () => {
  expect(easeInOutCubic(0)).toBe(0);
  expect(easeInOutCubic(0.5)).toBe(0.5);
  expect(easeInOutCubic(1)).toBe(1);
  expect(easeInOutCubic(0.25)).toBeLessThan(0.25);
});
