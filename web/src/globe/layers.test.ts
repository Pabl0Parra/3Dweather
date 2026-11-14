import { expect, test } from "vitest";
import { LAYERS, layerForPath, legendGradient, rampTable, type LayerId } from "./layers";

const IDS: LayerId[] = ["rain", "wind", "temperature", "waves", "currents"];

test("every layer has a path, a ramp and credits", () => {
  for (const id of IDS) {
    const l = LAYERS[id];
    expect(l.id).toBe(id);
    expect(l.path).toMatch(/^\/[a-z-]+-map$/);
    expect(l.ramp.length).toBeGreaterThanOrEqual(5);
    for (let i = 1; i < l.ramp.length; i++) expect(l.ramp[i][0]).toBeGreaterThan(l.ramp[i - 1][0]);
    expect(l.credits.length).toBeGreaterThan(10);
  }
});

test("paths map to layers; unknown paths fall back to waves", () => {
  expect(layerForPath("/weather-map")).toBe("rain");
  expect(layerForPath("/wind-map/")).toBe("wind");
  expect(layerForPath("/temperature-map")).toBe("temperature");
  expect(layerForPath("/ocean-currents-map")).toBe("currents");
  expect(layerForPath("/nope")).toBe("waves");
});

test("ramp tables have 256 entries and start at the calm colour", () => {
  for (const id of IDS) {
    const t = rampTable(LAYERS[id]);
    expect(t.length).toBe(1024);
  }
  const w = rampTable(LAYERS.wind);
  expect([...w.slice(0, 4)]).toEqual([...LAYERS.wind.ramp[0][1]]);
});

test("the wave ramp table is unchanged", async () => {
  const { rampTable: waveTable } = await import("./ramp");
  expect([...rampTable(LAYERS.waves)]).toEqual([...waveTable()]);
});

test("vector layers index the ramp by speed on a square-root scale", () => {
  const l = LAYERS.wind;
  const t = rampTable(l);
  // byte index i means speed (i/255)^2 * max
  const i = Math.round(Math.sqrt(20 / l.vecMax!) * 255);
  expect(t[i * 4 + 3]).toBeGreaterThan(0);
});

import { legendScale } from "./layers";
import { DEFAULT_UNITS } from "./units";

test("legend ticks follow the layer and the units", () => {
  const wind = legendScale(LAYERS.wind, DEFAULT_UNITS);
  expect(wind.unit).toBe("kn");
  expect(wind.ticks.map(([, l]) => l)).toEqual(["10", "20", "40", "60"]);
  const windKmh = legendScale(LAYERS.wind, { ...DEFAULT_UNITS, speed: "kmh" });
  expect(windKmh.ticks.map(([, l]) => l)).toEqual(["20", "40", "80", "120"]);
  const temp = legendScale(LAYERS.temperature, { ...DEFAULT_UNITS, temp: "F" });
  expect(temp.unit).toBe("°F");
  expect(temp.ticks[0][0]).toBeCloseTo((0 - 32) * 5 / 9, 6); // positions stay in °C
  const rain = legendScale(LAYERS.rain, { ...DEFAULT_UNITS, length: "ft" });
  expect(rain.unit).toBe("in/h");
  const waves = legendScale(LAYERS.waves, DEFAULT_UNITS);
  expect(waves.ticks.map(([, l]) => l)).toEqual(["1", "3", "6", "9", "12"]);
  for (const id of ["rain", "wind", "temperature", "waves", "currents"] as const) {
    const s = legendScale(LAYERS[id], DEFAULT_UNITS);
    for (const [v] of s.ticks) expect(s.pos(v)).toBeGreaterThanOrEqual(0), expect(s.pos(v)).toBeLessThanOrEqual(100);
  }
});

test("legend gradient places each ramp stop on the legend's own scale", () => {
  const g = legendGradient(LAYERS.waves);
  expect(g.startsWith("rgb(")).toBe(true);
  expect(g).toContain(" 0.0%");
  expect(g.endsWith("100.0%")).toBe(true);
  const t = legendGradient(LAYERS.temperature);
  expect(t.split(", rgb").length).toBe(LAYERS.temperature.ramp.length);
});
