import { expect, test } from "vitest";
import { phasesAt, tideAt, type TideAtlas } from "./tide";

const SPEED_M2 = (28.9841042 * Math.PI) / 180;
const START = Date.UTC(2026, 0, 1);

/** 8x4 cells of 45 deg; only M2 is non-zero: A = 2 m everywhere at sea, phase lag G. */
function atlas(G: number, opts: { landAt?: [number, number] } = {}): TideAtlas {
  const w = 8, h = 4, tiles = 6;
  const px = new Uint8ClampedArray(w * h * tiles * 4);
  const amax = { m2: 2, s2: 1, n2: 1, k2: 1, k1: 1, o1: 1, p1: 1, q1: 1 };
  for (let ch = 0; ch < 18; ch++) {
    const tile = Math.floor(ch / 3), comp = ch % 3;
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        let v = 128;
        if (ch === 0) v = Math.round(Math.cos(G) * 127) + 128;
        if (ch === 1) v = Math.round(Math.sin(G) * 127) + 128;
        if (ch === 16) v = opts.landAt && opts.landAt[0] === x && opts.landAt[1] === y ? 0 : 255;
        if (ch === 17) v = 0;
        px[((tile * h + y) * w + x) * 4 + comp] = v;
        px[((tile * h + y) * w + x) * 4 + 3] = 255;
      }
  }
  // Month 0: f = 1, V+u = 0 at the start; month 1 continues the phase exactly.
  const m0 = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0];
  const hoursJan = 31 * 24;
  const m1 = m0.slice();
  m1[1] = ((SPEED_M2 * hoursJan + Math.PI) % (2 * Math.PI)) - Math.PI;
  return {
    source: "test", cons: ["m2", "s2", "n2", "k2", "k1", "o1", "p1", "q1"], w, h, tiles,
    west: -157.5, north: 67.5, dlon: 45, dlat: 45, amax, start: "2026-01-01T00:00:00Z",
    speed: [SPEED_M2, 0, 0, 0, 0, 0, 0, 0], months: [m0, m1], pixels: px,
  };
}

const at = (hours: number) => new Date(START + hours * 3.6e6);
const near = (a: number, b: number, tol: number) => expect(Math.abs(a - b)).toBeLessThanOrEqual(tol);

test("height is A cos(V+u - G): a phase lag delays high water", () => {
  const G = Math.PI / 3;
  const a = atlas(G);
  for (const hours of [0, 2, 5.5, 9]) {
    const want = 2 * Math.cos(SPEED_M2 * hours - G);
    near(tideAt(a, 22.5, 22.5, at(hours))!.heightM, want, 0.03);
  }
  // high water when V = G, i.e. G / speed hours after the start
  near(tideAt(a, 22.5, 22.5, at(G / SPEED_M2))!.heightM, 2, 0.03);
});

test("phases from the monthly table: c and s carry amax and f", () => {
  const p = phasesAt(atlas(0), at(3));
  near(p.c[0], 2 * Math.cos(SPEED_M2 * 3), 1e-9);
  near(p.s[0], 2 * Math.sin(SPEED_M2 * 3), 1e-9);
  expect(p.c.length).toBe(8);
});

test("the phase is continuous across a month start", () => {
  const a = atlas(0);
  const before = tideAt(a, 22.5, 22.5, new Date(Date.UTC(2026, 1, 1) - 1000))!.heightM;
  const after = tideAt(a, 22.5, 22.5, new Date(Date.UTC(2026, 1, 1) + 1000))!.heightM;
  near(before, after, 0.01);
});

test("times outside the table are clamped, never NaN", () => {
  const a = atlas(0);
  expect(Number.isFinite(tideAt(a, 22.5, 22.5, new Date(Date.UTC(2019, 5, 1)))!.heightM)).toBe(true);
  expect(Number.isFinite(tideAt(a, 22.5, 22.5, new Date(Date.UTC(2040, 5, 1)))!.heightM)).toBe(true);
});

test("land cells give null", () => {
  // cell x=4 (lon 22.5), y=1 (lat 22.5)
  expect(tideAt(atlas(0, { landAt: [4, 1] }), 22.5, 22.5, at(0))).toBeNull();
});

test("sampling wraps at the antimeridian", () => {
  const a = atlas(0.7);
  const e = tideAt(a, 22.5, 179.9, at(1))!.heightM, w = tideAt(a, 22.5, -179.9, at(1))!.heightM;
  near(e, w, 0.01);
});

test("rising compares with ten minutes later", () => {
  const a = atlas(0);
  // just after high water (V = 0) the tide falls; just before the next one it rises
  expect(tideAt(a, 22.5, 22.5, at(0.5))!.rising).toBe(false);
  expect(tideAt(a, 22.5, 22.5, at(11))!.rising).toBe(true);
});

test("next to land the height comes from the sea cells only, not pulled toward zero", () => {
  const a = atlas(0, { landAt: [3, 1] });
  const { w, h } = a;
  a.pixels[((0 * h + 1) * w + 3) * 4 + 0] = 128; // land cells store X = Y = 0
  a.pixels[((0 * h + 1) * w + 3) * 4 + 1] = 128;
  // lon -55 sits 28 % of the way from the sea cell (x=2, lon -67.5) to the land cell (x=3)
  near(tideAt(a, 22.5, -55, at(0))!.heightM, 2, 0.03);
});

import { highestTide } from "./tide";

test("highest tide now: the sea cell with the greatest height", () => {
  const a = atlas(Math.PI / 2); // at t = 0 every cell reads 0 m ...
  // ... except one whose X byte is raised to the top: X byte 255 at x=2, y=2 (lon -67.5, lat -22.5)
  const w = a.w, h = a.h;
  a.pixels[((0 * h + 2) * w + 2) * 4 + 0] = 255;
  const top = highestTide(a, at(0))!;
  expect(top.lat).toBeCloseTo(-22.5, 6);
  expect(top.lon).toBeCloseTo(-67.5, 6);
  expect(top.heightM).toBeGreaterThan(1.99);
});
