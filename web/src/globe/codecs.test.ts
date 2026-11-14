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
