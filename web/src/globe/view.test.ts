import { expect, test } from "vitest";
import { clampView, project, radiusPx, rotateBy, unproject } from "./view";

const V = { lat0: 0, lon0: 0, zoom: 1 };
const W = 800;
const H = 600;

test("centre projects to screen centre", () => {
  expect(project(V, W, H, 0, 0)).toEqual({ x: 400, y: 300, visible: true });
});

test("radius formula", () => {
  expect(radiusPx(2, 800, 600)).toBeCloseTo(2 * 0.45 * 584);
});

test("90 degrees east lands on the right edge; far side invisible", () => {
  const p = project(V, W, H, 0, 90);
  expect(p.x).toBeCloseTo(400 + radiusPx(1, W, H));
  expect(p.y).toBeCloseTo(300);
  expect(project(V, W, H, 0, 180).visible).toBe(false);
});

test("north is up", () => {
  expect(project(V, W, H, 45, 0).y).toBeLessThan(300);
});

test("unproject inverts project on the near side", () => {
  const v = { lat0: 44.5, lon0: 9.5, zoom: 2.7 };
  const p = project(v, W, H, 50, 20);
  const q = unproject(v, W, H, p.x, p.y)!;
  expect(q.lat).toBeCloseTo(50, 6);
  expect(q.lon).toBeCloseTo(20, 6);
});

test("unproject outside the disk is null", () => {
  expect(unproject(V, W, H, 5, 5)).toBeNull();
});

test("clampView limits and wraps", () => {
  expect(clampView({ lat0: 120, lon0: 190, zoom: 99 })).toEqual({ lat0: 85, lon0: -170, zoom: 16 });
});

test("dragging right moves the view west", () => {
  expect(rotateBy(V, 10, 0, W, H).lon0).toBeLessThan(0);
});
