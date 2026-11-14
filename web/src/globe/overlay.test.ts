import { describe, expect, test } from "vitest";
import { visibleRuns } from "./overlay";

describe("visibleRuns", () => {
  test("a line crossing the horizon is split into near-side runs", () => {
    const runs = visibleRuns({ lat0: 0, lon0: 0, zoom: 1 }, 800, 600, [60, 0, 80, 0, 100, 0, 120, 0]);
    expect(runs.length).toBe(1);
    expect(runs[0].length).toBe(2);
  });

  test("a line that leaves and comes back gives two runs", () => {
    const runs = visibleRuns({ lat0: 0, lon0: 0, zoom: 1 }, 800, 600, [60, 0, 120, 0, 180, 0, -120, 0, -60, 0]);
    expect(runs.map((r) => r.length)).toEqual([1, 1]);
  });

  test("points are in screen pixels", () => {
    const [[p]] = visibleRuns({ lat0: 0, lon0: 0, zoom: 1 }, 800, 600, [0, 0, 1, 0]);
    expect(p[0]).toBeCloseTo(400);
    expect(p[1]).toBeCloseTo(300);
  });
});
