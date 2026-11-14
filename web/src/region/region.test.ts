import { expect, test } from "vitest";
import { clampFlat, fitScale, projectFlat, unprojectFlat, type FlatGeom } from "./flat";
import { frameCount, sheetIndex, type RegionManifest } from "./sheet";
import { fieldPixels, sampleRegion } from "./field";
import { nearestCity, peakSummary } from "./summary";
import { REGIONS } from "./regions";
import { LAYERS } from "../globe/layers";
import { DEFAULT_UNITS } from "../globe/units";

const M: RegionManifest = {
  region: "test", run: "2026-11-13T06:00Z", hours: 73, cols: 8, w: 4, h: 3,
  north: 52, south: 48, west: -4, east: 2, focus: [-3, 48.5, 1, 51.5], tz: "Europe/London", place: "London",
  cities: [["London", 51.5, -0.13], ["Paris", 48.86, 2.35], ["Brest", 48.39, -4.49]],
  peaks: {
    wind: Array.from({ length: 73 }, (_, h) => [h === 27 ? 31.9 : 20, 50.0, -1.0]),
    rain: Array.from({ length: 73 }, (_, h) => [h === 72 ? 14 : 2, 49.0, 1.5]),
  },
  masked: false,
};

const geom = (w = 800, h = 600): FlatGeom => ({ m: M, w, h });

test("flat projection: focus box fills the view at zoom 1 and round-trips", () => {
  const g = geom();
  const k = Math.cos((50 * Math.PI) / 180);
  expect(fitScale(g)).toBeCloseTo(Math.min(800 / (4 * k), 600 / 3), 9);
  const v = { lon0: -1, lat0: 50, zoom: 2 };
  const p = projectFlat(v, g, 51, 0.5);
  const back = unprojectFlat(v, g, p.x, p.y);
  expect(back.lat).toBeCloseTo(51, 9);
  expect(back.lon).toBeCloseTo(0.5, 9);
  expect(projectFlat(v, g, 50, -1)).toEqual({ x: 400, y: 300 });
});

test("flat view is clamped to the grid and to zoom 1..8", () => {
  const g = geom();
  const c = clampFlat({ lon0: 50, lat0: 80, zoom: 20 }, g);
  expect(c.zoom).toBe(8);
  expect(c.lon0).toBeLessThanOrEqual(2);
  expect(c.lat0).toBeLessThanOrEqual(52);
  const out = clampFlat({ lon0: 0, lat0: 0, zoom: 0.1 }, g);
  expect(out.zoom).toBe(1);
});

test("sheet index: frame j sits at column j % 8, row j / 8", () => {
  expect(frameCount(M)).toBe(73);
  const sheetW = 8 * M.w;
  // frame 9 -> column 1, row 1; cell (x=2, y=1)
  expect(sheetIndex(M, sheetW, 9, 2, 1)).toBe(((1 * M.h + 1) * sheetW + (1 * M.w + 2)) * 4);
});

function sheets(fill: (j: number, x: number, y: number) => [number, number, number, number, number]) {
  const W = 8 * M.w, H = 10 * M.h;
  const a = new Uint8ClampedArray(W * H * 4), b = new Uint8ClampedArray(W * H * 4);
  for (let j = 0; j < 73; j++)
    for (let y = 0; y < M.h; y++)
      for (let x = 0; x < M.w; x++) {
        const i = sheetIndex(M, W, j, x, y);
        const [u, v, rain, cloud] = fill(j, x, y);
        a.set([u, v, rain, 255], i);
        b.set([cloud, cloud, cloud, 255], i);
      }
  return { a: { pixels: a, width: W, height: H }, b: { pixels: b, width: W, height: H } };
}

test("sample decodes wind, rain and cloud and blends between hours", () => {
  // u byte 128 + 127*10/50 at hour 0, 128 at hour 1; rain byte 255 (64 mm/h) at hour 0
  const s = sheets((j) => [j === 0 ? 153 : 128, 128, j === 0 ? 255 : 0, j === 0 ? 255 : 0, 0]);
  const at0 = sampleRegion(s.a, s.b, M, 0, 50, -1)!;
  expect(at0.windMs!).toBeCloseTo(((153 - 128) * 50) / 127, 6);
  expect(at0.windFromDeg!).toBeCloseTo(270, 6); // blowing toward the east comes from the west
  expect(at0.rainMmh!).toBeCloseTo(64, 6);
  expect(at0.cloudPct!).toBeCloseTo(100, 6);
  const half = sampleRegion(s.a, s.b, M, 0.5, 50, -1)!;
  expect(half.cloudPct!).toBeCloseTo(50, 1);
  expect(sampleRegion(s.a, s.b, M, 0, 60, -1)).toBeNull(); // outside the grid
});

test("field pixels: rain layer paints rain over a cloud veil; wind layer uses the speed ramp", () => {
  const s = sheets(() => [128, 128, 0, 255, 0]); // full cloud, no rain
  const cloudOnly = fieldPixels(s.a, s.b, M, 0, LAYERS.rain);
  expect(cloudOnly.length).toBe(M.w * M.h * 4);
  expect(cloudOnly[3]).toBeGreaterThan(100); // a white veil
  expect(cloudOnly[0]).toBeGreaterThan(200);
  const calm = fieldPixels(s.a, s.b, M, 0, LAYERS.wind);
  const windy = fieldPixels(sheets(() => [255, 128, 0, 0, 0]).a, s.b, M, 0, LAYERS.wind);
  expect(Array.from(windy.slice(0, 3))).not.toEqual(Array.from(calm.slice(0, 3)));
});

test("peak summary names the time in the region's zone and the nearest city", () => {
  const s = peakSummary(M, DEFAULT_UNITS);
  expect(s.wind.value).toBe("62 kn");
  expect(s.wind.when).toBe("Sat 14 Nov, 09:00"); // hour 27 = 14 Nov 09:00 UTC = London time
  expect(s.wind.where).toMatch(/^about \d+ km from (London|Brest|Paris)$/);
  expect(s.rain.value).toBe("14.0 mm/h");
  expect(s.rain.when).toBe("Mon 16 Nov, 06:00");
  const india = peakSummary({ ...M, tz: "Asia/Kolkata" }, DEFAULT_UNITS);
  expect(india.wind.when).toBe("Sat 14 Nov, 14:30"); // a half-hour zone
  expect(nearestCity(M, 48.4, -4.4).name).toBe("Brest");
});

test("every region's time zone is a real zone", () => {
  expect(REGIONS).toHaveLength(12);
  for (const r of REGIONS) expect(() => new Intl.DateTimeFormat("en-GB", { timeZone: r.tz })).not.toThrow();
});
