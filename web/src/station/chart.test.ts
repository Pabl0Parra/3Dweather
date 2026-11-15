import { describe, expect, it } from "vitest";
import { chartPath, cosineHeight, curveSlice } from "./chart";
import type { StationData, Turn } from "./format";

const SIZE = { w: 600, h: 200, lo: -1, hi: 1 };
const turns: Turn[] = [["00:00", 0, 0.5, 1], ["06:12", 372, -0.5, 0], ["12:25", 745, 0.6, 1], ["18:40", 1120, -0.4, 0]];
const day = { date: "2026-11-15", day_minutes: 1440, tides: turns };

function pathPoints(path: string): [number, number][] {
  return path.replace(/^M/, "").split("L").map((p) => p.split(",").map(Number) as [number, number]);
}

describe("tide chart", () => {
  it("passes through every turn and spans the day (cosine fallback)", () => {
    const r = chartPath(day, null, turns, SIZE);
    const pts = pathPoints(r.path);
    expect(pts[0][0]).toBeCloseTo(0);
    expect(pts[pts.length - 1][0]).toBeCloseTo(600);
    expect(r.marks.map((m) => m.hi)).toEqual([true, false, true, false]);
    for (const m of r.marks) {
      const near = pts.reduce((a, p) => (Math.abs(p[0] - m.x) < Math.abs(a[0] - m.x) ? p : a));
      expect(Math.abs(near[1] - m.y)).toBeLessThan(1.5);
    }
  });

  it("is monotonic between turns with the cosine fallback", () => {
    let last = cosineHeight(turns, 0);
    for (let t = 10; t <= 372; t += 10) {
      const h = cosineHeight(turns, t);
      expect(h).toBeLessThanOrEqual(last + 1e-9);
      last = h;
    }
    expect(cosineHeight(turns, 372)).toBeCloseTo(-0.5);
  });

  it("uses the embedded 10-minute curve for days it covers", () => {
    const cm = Array.from({ length: 433 }, (_, k) => k);
    const curve: StationData["curve"] = { from: "2026-11-14", step_min: 10, days: [1440, 1440, 1440], cm };
    expect(curveSlice(curve, "2026-11-15", 1440)).toEqual(cm.slice(144, 289).map((v) => v / 100));
    expect(curveSlice(curve, "2026-11-20", 1440)).toBeNull();
    const r = chartPath(day, curve, turns, { w: 600, h: 200, lo: 0, hi: 5 });
    expect(pathPoints(r.path).length).toBe(145);
  });
});
