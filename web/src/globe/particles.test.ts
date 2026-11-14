import { expect, test } from "vitest";
import { LandGrid } from "./field";
import { flowSteps, particleCount, Particles, segmentOk, spawnOnDisk, stepPoint } from "./particles";
import { project } from "./view";

const seq = (x: number) => () => x;

test("count follows disk area within limits", () => {
  expect(particleCount(95 * 1000, 1200)).toBe(1000);
  expect(particleCount(10, 1200)).toBe(400);
  expect(particleCount(1e9, 1200)).toBe(5000);
  expect(particleCount(1e9, 600)).toBe(2400);
});

test("east-west steps stretch with latitude", () => {
  const [, lonEq] = stepPoint(0, 0, 1, 0), [, lon60] = stepPoint(60, 0, 1, 0);
  expect(lon60).toBeCloseTo(lonEq * 2, 5);
});

test("north steps move latitude only", () => {
  const [lat, lon] = stepPoint(10, 20, 0, 0.5);
  expect(lat).toBeGreaterThan(10);
  expect(lon).toBeCloseTo(20);
});

test("steps wrap longitude", () => {
  expect(stepPoint(0, 179.99, 1, 0)[1]).toBeLessThan(-179);
});

test("calm water does not move", () => {
  expect(stepPoint(5, 5, 0, 0)).toEqual([5, 5]);
});

test("particles on land respawn", () => {
  const p = new Particles(seq(0.1));
  p.resize(1, () => [10, 10]);
  p.step(() => null, () => [-20, -30], () => false);
  expect(p.head(0)).toEqual([-20, -30]);
});

test("particles move with the field", () => {
  const p = new Particles(seq(0.5));
  p.resize(1, () => [0, 0]);
  p.step(() => ({ u: 1, v: 0 }), () => [50, 50], () => false);
  const [lat, lon] = p.head(0);
  expect(lat).toBeCloseTo(0);
  expect(lon).toBeGreaterThan(0);
});

test("trail segments longer than 0.25 R are not drawn", () => {
  expect(segmentOk(0, 0, 10, 0, 100)).toBe(true);
  expect(segmentOk(0, 0, 26, 0, 100)).toBe(false); // e.g. a wrap across the limb
});

test("spawn lands on the visible sea", () => {
  const land = new LandGrid(Uint8Array.from([255, 0]), 2, 1); // west half land
  let k = 0;
  const rand = () => ((k = (k * 9301 + 49297) % 233280) / 233280);
  for (let i = 0; i < 20; i++) {
    const [lat, lon] = spawnOnDisk({ lat0: 0, lon0: 0, zoom: 1 }, 800, 600, land, rand);
    expect(land.isLand(lat, lon)).toBe(false);
    expect(project({ lat0: 0, lon0: 0, zoom: 1 }, 800, 600, lat, lon).visible).toBe(true);
  }
});

test("reduced motion pre-runs trails only for fresh particles", () => {
  expect(flowSteps(true, true)).toBe(14);
  expect(flowSteps(true, false)).toBe(1);
  expect(flowSteps(false, true)).toBe(1);
  expect(flowSteps(false, false)).toBe(1);
});
