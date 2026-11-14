import { expect, test } from "vitest";
import type { FramePairPixels } from "./frames";
import { LAYERS } from "./layers";
import { flowVector, sampleLayer, type Sample } from "./field";
import type { GlobeManifest } from "./manifest";
import { readoutFor } from "./probe";
import { DEFAULT_UNITS, type Units } from "./units";

const M = { w: 4, h: 2, west: -135, dlon: 90, north: 45, dlat: 90, gustHours: 84 } as GlobeManifest;

function flat(r: number, g: number, b: number): FramePairPixels {
  const px = new Uint8ClampedArray(4 * 2 * 4);
  for (let i = 0; i < 8; i++) px.set([r, g, b, 255], i * 4);
  return { a: px, b: px, mix: 0, fa: 0, fb: 1 };
}

const C = "45.00° N, 45.00° W";
const IMPERIAL: Units = { length: "ft", speed: "mph", temp: "F" };

test("wind readout with gusts, then without them past 84 h", () => {
  // u = -10 m/s, v = -10 m/s: blowing toward SW, so from NE
  const frames = { a: flat(103, 103, 0), b: flat(0, 128, 85) }; // gust byte 85 = 20 m/s
  const s = sampleLayer(LAYERS.wind, frames, M, 45, -45, 12);
  expect(s.windFromDeg).toBeCloseTo(45, 0);
  expect(readoutFor(LAYERS.wind, s, 45, -45, DEFAULT_UNITS)).toEqual(["Wind 27 kn from NE (45°)", "Gusts 39 kn", C]);
  const late = sampleLayer(LAYERS.wind, frames, M, 45, -45, 90);
  expect(late.gustMs).toBeUndefined();
  expect(readoutFor(LAYERS.wind, late, 45, -45, IMPERIAL)).toEqual(["Wind 31 mph from NE (45°)", C]);
});

test("calm wind", () => {
  const s = sampleLayer(LAYERS.wind, { a: flat(128, 128, 0), b: flat(0, 0, 0) }, M, 45, -45, 0);
  expect(readoutFor(LAYERS.wind, s, 45, -45, DEFAULT_UNITS)[0]).toBe("Calm");
});

test("rain and cloud", () => {
  const s = sampleLayer(LAYERS.rain, { a: flat(128, 128, 64), b: flat(153, 0, 0) }, M, 45, -45, 0);
  expect(readoutFor(LAYERS.rain, s, 45, -45, DEFAULT_UNITS)).toEqual(["Rain 4.0 mm/h", "Cloud 60 %", C]);
  const dry = sampleLayer(LAYERS.rain, { a: flat(128, 128, 0), b: flat(0, 0, 0) }, M, 45, -45, 0);
  expect(readoutFor(LAYERS.rain, dry, 45, -45, DEFAULT_UNITS)).toEqual(["No rain", "Cloud 0 %", C]);
});

test("air temperature", () => {
  const s = sampleLayer(LAYERS.temperature, { t: flat(174, 0, 0), a: flat(128, 128, 0) }, M, 45, -45, 0);
  expect(readoutFor(LAYERS.temperature, s, 45, -45, DEFAULT_UNITS)).toEqual(["Air 15 °C", C]);
  expect(readoutFor(LAYERS.temperature, s, 45, -45, IMPERIAL)).toEqual(["Air 59 °F", C]);
});

test("currents and sea temperature; slack water; land", () => {
  // u = +1 m/s east, v = 0; sea byte 156 = 20 °C
  const s = sampleLayer(LAYERS.currents, { c: flat(179, 128, 156) }, M, 45, -45, 0);
  expect(readoutFor(LAYERS.currents, s, 45, -45, DEFAULT_UNITS)).toEqual(["Current 2.0 kn toward E", "Sea 20 °C", C]);
  const slack = sampleLayer(LAYERS.currents, { c: flat(128, 128, 156) }, M, 45, -45, 0);
  expect(readoutFor(LAYERS.currents, slack, 45, -45, DEFAULT_UNITS)[0]).toBe("Slack");
  expect(readoutFor(LAYERS.currents, null, 45, -45, DEFAULT_UNITS)).toEqual(["Land — no current data", C]);
});

test("waves keep their readout", () => {
  const s: Sample = sampleLayer(LAYERS.waves, { w: flat(100, 179, 128) }, M, 45, -45, 0);
  expect(readoutFor(LAYERS.waves, s, 45, -45, DEFAULT_UNITS)[1]).toBe("Period 10 s");
  expect(readoutFor(LAYERS.waves, null, 45, -45, DEFAULT_UNITS)).toEqual(["Land — no wave data", C]);
});

test("particle vectors are scaled per layer and never NaN", () => {
  const wind = flowVector(LAYERS.wind, { a: flat(128 + 127, 128, 0) }, M, 45, -45)!; // u = 50 m/s
  expect(wind.u).toBeCloseTo(2, 5);
  expect(flowVector(LAYERS.wind, { a: flat(128, 128, 0) }, M, 45, -45)).toEqual({ u: 0, v: 0 });
  expect(flowVector(LAYERS.currents, { c: flat(179, 128, 0) }, M, 45, -45)!.u).toBeCloseTo(1.004, 2);
  expect(flowVector(LAYERS.currents, {}, M, 45, -45)).toBeNull();
});
