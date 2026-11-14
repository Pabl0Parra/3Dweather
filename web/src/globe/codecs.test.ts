import { expect, test } from "vitest";
import { decodeHeight, decodeWave } from "./codecs";

test("height byte 237 is 13.82 m", () => {
  expect(decodeHeight(237)).toBeCloseTo(13.82, 2);
});

test("waves travelling east come from the west, period from length", () => {
  const w = decodeWave(179, 128);
  expect(w.fromDeg).toBeCloseTo(270, 0);
  expect(w.periodS).toBeCloseTo(10.0, 1);
});

test("travelling south means from north", () => {
  expect(decodeWave(128, 1).fromDeg).toBeCloseTo(0, 0);
});

import { decodeAirTemp, decodeCloud, decodeCurrent, decodeGust, decodePressure, decodeRain, decodeSeaTemp, decodeWind } from "./codecs";

test("byte decodes match pipeline/codecs.py", () => {
  expect(decodeWind(128)).toBe(0);
  expect(decodeWind(255)).toBeCloseTo(50, 6);
  expect(decodeWind(1)).toBeCloseTo(-50, 6);
  expect(decodeGust(255)).toBeCloseTo(60, 6);
  expect(decodeRain(255)).toBeCloseTo(64, 6);
  expect(decodeRain(128)).toBeCloseTo((128 / 255) ** 2 * 64, 6);
  expect(decodeAirTemp(0)).toBe(-60);
  expect(decodeAirTemp(255)).toBeCloseTo(50, 6);
  expect(decodeSeaTemp(0)).toBe(-2);
  expect(decodeSeaTemp(255)).toBeCloseTo(34, 6);
  expect(decodeCurrent(255)).toBeCloseTo(2.5, 6);
  expect(decodePressure(1)).toBe(940);
  expect(decodePressure(255)).toBeCloseTo(1060, 6);
  expect(decodePressure(0)).toBeNull();
  expect(decodeCloud(255)).toBeCloseTo(100, 6);
});
