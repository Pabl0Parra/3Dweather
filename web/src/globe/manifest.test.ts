import { expect, test } from "vitest";
import { chunkSlot, framePair, type GlobeManifest } from "./manifest";

const M = { every: 3, hours: 168, frames: 57, chunks: [8, 8, 8, 8, 8, 8, 9] } as GlobeManifest;

test("frame pairs", () => {
  expect(framePair(M, 0)).toEqual({ a: 0, b: 1, mix: 0 });
  expect(framePair(M, 4.5)).toEqual({ a: 1, b: 2, mix: 0.5 });
  expect(framePair(M, 168)).toEqual({ a: 56, b: 56, mix: 0 });
  expect(framePair(M, -5)).toEqual({ a: 0, b: 1, mix: 0 });
});

test("chunk slots", () => {
  expect(chunkSlot(M, 7)).toEqual({ chunk: 0, slot: 7 });
  expect(chunkSlot(M, 48)).toEqual({ chunk: 6, slot: 0 });
  expect(chunkSlot(M, 56)).toEqual({ chunk: 6, slot: 8 });
});

import { sheetFor } from "./manifest";

const MC = { ...M, w: 768, h: 384, cols: 4, currentEvery: 24, currentFrames: 8 } as GlobeManifest;

test("the ocean sheet is one file of 8 daily frames", () => {
  const c = sheetFor(MC, "c");
  expect(c.chunks).toEqual([8]);
  expect(c.every).toBe(24);
  expect(c.frames).toBe(8);
  expect(c.url(0)).toBe("globe-c.webp");
  expect(framePair(c, 167.5)).toMatchObject({ a: 6, b: 7 });
  expect(framePair(c, 167.5).mix).toBeCloseTo(23.5 / 24, 9);
  expect(framePair(c, 168)).toEqual({ a: 7, b: 7, mix: 0 });
});

test("other sheets follow the manifest chunks", () => {
  const a = sheetFor(MC, "a");
  expect(a.chunks).toEqual([8, 8, 8, 8, 8, 8, 9]);
  expect(a.url(3)).toBe("globe-a3.webp");
});
