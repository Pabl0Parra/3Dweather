import { expect, test } from "vitest";
import { stepInertia, zoomBy } from "./gestures";

test("inertia decays and stops", () => {
  let v: { x: number; y: number } | null = { x: 10, y: 0 };
  let n = 0;
  while ((v = stepInertia(v))) n++;
  expect(n).toBeGreaterThan(75);
  expect(n).toBeLessThan(90); // 10 * 0.92^n < 0.01 at n ~ 83
});

test("zoomBy clamps", () => {
  expect(zoomBy({ lat0: 0, lon0: 0, zoom: 15 }, 2).zoom).toBe(16);
  expect(zoomBy({ lat0: 0, lon0: 0, zoom: 1 }, 0.1).zoom).toBe(0.75);
});

test("zoomBy keeps the centre", () => {
  expect(zoomBy({ lat0: 10, lon0: 20, zoom: 2 }, 1.25)).toEqual({ lat0: 10, lon0: 20, zoom: 2.5 });
});
