import { expect, test } from "vitest";
import { DEFAULT_UNITS, formatLength, formatSpeed, formatTemp, legendTicks, loadUnits, saveUnits } from "./units";

function fakeStorage(init: Record<string, string>): Storage {
  const m = new Map(Object.entries(init));
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) } as unknown as Storage;
}

test("lengths", () => {
  expect(formatLength(2.44, "m")).toBe("2.4 m");
  expect(formatLength(2.44, "ft")).toBe("8.0 ft");
});

test("speeds", () => {
  expect(formatSpeed(10, "kn")).toBe("19 kn");
  expect(formatSpeed(10, "kmh")).toBe("36 km/h");
  expect(formatSpeed(10, "ms")).toBe("10 m/s");
  expect(formatSpeed(10, "mph")).toBe("22 mph");
});

test("temperatures", () => {
  expect(formatTemp(18, "C")).toBe("18 °C");
  expect(formatTemp(18, "F")).toBe("64 °F");
});

test("storage that throws gives defaults", () => {
  const bad = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } } as unknown as Storage;
  expect(loadUnits(bad)).toEqual(DEFAULT_UNITS);
  expect(() => saveUnits(DEFAULT_UNITS, bad)).not.toThrow();
  expect(loadUnits(null)).toEqual(DEFAULT_UNITS);
});

test("bad stored values fall back per field", () => {
  const s = fakeStorage({ "3dw.units": JSON.stringify({ length: "ft", speed: "warp" }) });
  expect(loadUnits(s)).toEqual({ length: "ft", speed: "kn", temp: "C" });
  expect(loadUnits(fakeStorage({ "3dw.units": "{not json" }))).toEqual(DEFAULT_UNITS);
});

test("round trip", () => {
  const s = fakeStorage({});
  saveUnits({ length: "ft", speed: "mph", temp: "F" }, s);
  expect(loadUnits(s)).toEqual({ length: "ft", speed: "mph", temp: "F" });
});

test("legend ticks in feet sit at their metre positions", () => {
  expect(legendTicks("m")).toEqual([[1, "1"], [3, "3"], [6, "6"], [9, "9"], [12, "12"]]);
  expect(legendTicks("ft").map(([, t]) => t)).toEqual(["3", "10", "20", "30", "40"]);
  expect(legendTicks("ft")[1][0]).toBeCloseTo(3.048);
});
