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
