import { expect, test } from "vitest";
import { compass, formatCoord, readoutLines } from "./probe";
import { DEFAULT_UNITS } from "./units";

test("compass", () => {
  expect(compass(315)).toBe("NW");
  expect(compass(359)).toBe("N");
  expect(compass(22.4)).toBe("N");
  expect(compass(22.6)).toBe("NE");
  expect(compass(-45)).toBe("NW");
});

test("coords", () => {
  expect(formatCoord(44.28, -140.92)).toBe("44.28° N, 140.92° W");
  expect(formatCoord(-33.9, 18.4)).toBe("33.90° S, 18.40° E");
});

test("sea readout", () => {
  expect(readoutLines({ heightM: 2.44, periodS: 11.2, fromDeg: 315, u: 0, v: 0 }, 44.28, -140.92, DEFAULT_UNITS))
    .toEqual(["2.4 m", "Period 11 s", "From NW (315°)", "44.28° N, 140.92° W"]);
});

test("feet", () => {
  expect(readoutLines({ heightM: 2.44, periodS: 11.2, fromDeg: 315, u: 0, v: 0 }, 0, 0, { ...DEFAULT_UNITS, length: "ft" })[0]).toBe("8.0 ft");
});

test("calm water", () => {
  expect(readoutLines({ heightM: 0.01, periodS: 0, fromDeg: 0, u: 0, v: 0 }, 0, 0, DEFAULT_UNITS)[0]).toBe("Calm");
});

test("land readout", () => {
  expect(readoutLines(null, 40.4, -3.7, DEFAULT_UNITS)).toEqual(["Land — no wave data", "40.40° N, 3.70° W"]);
});

test("no NaN at the limb", () => {
  expect(readoutLines(null, 90, 180, DEFAULT_UNITS).join(" ")).not.toMatch(/NaN/);
  expect(readoutLines({ heightM: NaN, periodS: NaN, fromDeg: NaN, u: 0, v: 0 }, 0, 0, DEFAULT_UNITS).join(" ")).not.toMatch(/NaN/);
});
