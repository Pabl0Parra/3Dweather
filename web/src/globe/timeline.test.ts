import { expect, test } from "vitest";
import { advance, HOURS_PER_SECOND, initialHour, SPEEDS, timeLabel } from "./timeline";

const RUN = "2026-11-13T06:00Z";

test("constants", () => {
  expect(SPEEDS).toEqual([0.5, 1, 2]);
  expect(HOURS_PER_SECOND).toBe(1.5);
});

test("initial hour clamps", () => {
  expect(initialHour(RUN, new Date("2026-11-13T18:00Z"), 168)).toBe(12);
  expect(initialHour(RUN, new Date("2026-11-30T00:00Z"), 168)).toBe(168);
  expect(initialHour(RUN, new Date("2026-11-01T00:00Z"), 168)).toBe(0);
});

test("advance wraps", () => {
  expect(advance(10, 2, 1, 168)).toBeCloseTo(13);
  expect(advance(167, 2, 1, 168)).toBeCloseTo(0);
  expect(advance(10, 2, 2, 168)).toBeCloseTo(16);
});

test("labels", () => {
  const now = new Date("2026-11-13T06:00Z");
  expect(timeLabel(RUN, 12, now, "UTC")).toBe("Fri 13 Nov, 18:00 · in 12 h");
  expect(timeLabel(RUN, 0, now, "UTC")).toBe("Fri 13 Nov, 06:00 · now");
  expect(timeLabel(RUN, 72, now, "UTC")).toBe("Mon 16 Nov, 06:00 · in 3 days");
  expect(timeLabel(RUN, 126, now, "UTC")).toBe("Wed 18 Nov, 12:00 · in 5 days · less certain");
});

test("past labels", () => {
  const now = new Date("2026-11-14T06:00Z");
  expect(timeLabel(RUN, 12, now, "UTC")).toBe("Fri 13 Nov, 18:00 · 12 h ago");
});

import { midnights } from "./timeline";

test("midnights follow the given zone, half-hour zones included", () => {
  // run 13 Nov 06:00 UTC; London midnights at 14 Nov 00:00 UTC = hour 18, then 42, 66
  expect(midnights("2026-11-13T06:00Z", 72, "Europe/London")).toEqual([18, 42, 66]);
  // Kolkata is UTC+5:30: 14 Nov 00:00 local = 13 Nov 18:30 UTC = hour 12.5
  expect(midnights("2026-11-13T06:00Z", 72, "Asia/Kolkata")).toEqual([12.5, 36.5, 60.5]);
});
