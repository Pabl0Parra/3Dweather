import { expect, test } from "vitest";
import { rampTable } from "./ramp";

test("ramp table endpoints and a stop", () => {
  const t = rampTable();
  expect(t.length).toBe(1024);
  expect([...t.slice(0, 4)]).toEqual([12, 40, 80, 115]);
  expect([...t.slice(1020, 1024)]).toEqual([245, 235, 255, 247]);
  const i = 64; // decodeHeight(64) is about 1.0 m
  expect(Math.abs(t[i * 4] - 20)).toBeLessThanOrEqual(1);
});
