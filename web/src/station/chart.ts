// The day's tide curve as an SVG path: from the embedded 10-minute heights when the day is in
// the three-day curve, otherwise a half-cosine between consecutive highs and lows.
import type { StationData, Turn } from "./format";

export type ChartSize = { w: number; h: number; lo: number; hi: number }; // lo/hi: metres at the bottom/top
export type Mark = { x: number; y: number; hi: boolean; hm: string; h: number };

const STEP = 10;

/** Heights (m) for one local day from the curve, or null when the curve does not cover it. */
export function curveSlice(curve: StationData["curve"], date: string, dayMinutes: number): number[] | null {
  if (!curve) return null;
  const start = Date.parse(`${curve.from}T00:00:00Z`);
  const k = Math.round((Date.parse(`${date}T00:00:00Z`) - start) / 86400000);
  if (k < 0 || k >= curve.days.length || curve.days[k] !== dayMinutes) return null;
  const off = curve.days.slice(0, k).reduce((a, b) => a + b, 0) / curve.step_min;
  const out = curve.cm.slice(off, off + dayMinutes / curve.step_min + 1);
  if (out.length !== dayMinutes / curve.step_min + 1 || out.some((v) => v == null)) return null;
  return out.map((v) => (v as number) / 100);
}

/** Half-cosine between the turns around minute `t`; flat beyond the first and last turn. */
export function cosineHeight(turns: Turn[], t: number): number {
  if (!turns.length) return 0;
  if (t <= turns[0][1]) return turns[0][2];
  for (let i = 1; i < turns.length; i++) {
    const [, t2, h2] = turns[i];
    if (t <= t2) {
      const [, t1, h1] = turns[i - 1];
      return h1 + ((h2 - h1) * (1 - Math.cos((Math.PI * (t - t1)) / (t2 - t1)))) / 2;
    }
  }
  return turns[turns.length - 1][2];
}

/** `turns`: this day's turns plus its neighbours', minutes relative to this day's local midnight. */
export function chartPath(day: { date: string; day_minutes: number; tides: Turn[] }, curve: StationData["curve"],
                          turns: Turn[], size: ChartSize): { path: string; marks: Mark[] } {
  const n = day.day_minutes;
  const x = (m: number) => (m / n) * size.w;
  const y = (h: number) => size.h - ((h - size.lo) / (size.hi - size.lo)) * size.h;
  const heights = curveSlice(curve, day.date, n)
    ?? Array.from({ length: Math.floor(n / STEP) + 1 }, (_, k) => cosineHeight(turns, Math.min(n, k * STEP)));
  const step = n / (heights.length - 1);
  const path = "M" + heights.map((h, k) => `${x(k * step).toFixed(1)},${y(h).toFixed(1)}`).join("L");
  const marks = day.tides.map(([hm, m, h, hi]) => ({ x: x(m), y: y(h), hi: hi === 1, hm, h }));
  return { path, marks };
}
