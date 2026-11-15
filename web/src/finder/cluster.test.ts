import { describe, expect, it } from "vitest";
import { clusterPoints } from "./cluster";

const p = (lat: number, lon: number, name = "x") => ({ lat, lon, name, path: `p/${name}` });

describe("finder clustering", () => {
  it("merges points in one cell at their mean position and keeps far points apart", () => {
    const out = clusterPoints([p(50, 0, "a"), p(50.001, 0.001, "b"), p(-30, 120, "c")], 4);
    expect(out.length).toBe(2);
    const big = out.find((c) => c.n === 2)!;
    expect(big.lat).toBeCloseTo(50.0005, 4);
    expect(big.path).toBeUndefined();
    const one = out.find((c) => c.n === 1)!;
    expect(one).toMatchObject({ name: "c", path: "p/c", lat: -30, lon: 120 });
  });

  it("splits clusters as the zoom grows and the counts always sum", () => {
    const pts = Array.from({ length: 200 }, (_, k) => p(40 + (k % 20) * 0.05, -74 + Math.floor(k / 20) * 0.05, `s${k}`));
    const z3 = clusterPoints(pts, 3), z12 = clusterPoints(pts, 12);
    expect(z3.length).toBeLessThan(z12.length);
    expect(z3.reduce((a, c) => a + c.n, 0)).toBe(200);
    expect(z12.reduce((a, c) => a + c.n, 0)).toBe(200);
  });
});
