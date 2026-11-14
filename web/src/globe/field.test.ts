import { expect, test } from "vitest";
import { decodeHeight } from "./codecs";
import { LandGrid, sampleWave } from "./field";
import type { GlobeManifest } from "./manifest";

// Toy 4x2 grid: cell centres at lon -135, -45, 45, 135 and lat 45, -45.
const M = { w: 4, h: 2, west: -135, dlon: 90, north: 45, dlat: 90 } as GlobeManifest;

function frame(r: number[], g = 128, b = 128): Uint8ClampedArray {
  const px = new Uint8ClampedArray(4 * 2 * 4);
  r.forEach((v, i) => { px[i * 4] = v; px[i * 4 + 1] = g; px[i * 4 + 2] = b; px[i * 4 + 3] = 255; });
  return px;
}

const A_R = [10, 255, 60, 90, 0, 0, 0, 0];
const A = frame(A_R);

test("samples a cell centre exactly", () => {
  expect(sampleWave(A, A, 0, M, 45, -45).heightM).toBeCloseTo(16);
});

test("wraps across the antimeridian", () => {
  expect(sampleWave(A, A, 0, M, 45, 180).heightM).toBeCloseTo(decodeHeight((A_R[3] + A_R[0]) / 2));
});

test("blends in time", () => {
  const zero = frame(Array(8).fill(0)), full = frame(Array(8).fill(255));
  expect(sampleWave(zero, full, 0.5, M, 45, -45).heightM).toBeCloseTo(decodeHeight(127.5));
});

test("vector points where waves travel", () => {
  const east = frame(Array(8).fill(100), 255, 128);
  const s = sampleWave(east, east, 0, M, 45, -45);
  expect(s.u).toBeCloseTo(1);
  expect(s.v).toBeCloseTo(0);
  expect(s.fromDeg).toBeCloseTo(270);
  expect(s.periodS).toBeCloseTo(25);
});

test("clamps beyond the last row", () => {
  expect(sampleWave(A, A, 0, M, 89, -45).heightM).toBeCloseTo(16);
  expect(Number.isFinite(sampleWave(A, A, 0, M, -90, 0).heightM)).toBe(true);
});

test("land grid lookup", () => {
  const g = new LandGrid(Uint8Array.from([255, 0, 0, 0, 0, 0, 0, 0]), 2, 1);
  expect(g.isLand(0, -90)).toBe(true);
  expect(g.isLand(0, 90)).toBe(false);
  expect(g.isLand(0, 180)).toBe(true); // wraps to the left edge
  expect(g.isLand(90, -90)).toBe(true);
});
