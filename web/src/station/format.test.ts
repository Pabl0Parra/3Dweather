import { describe, expect, it } from "vitest";
import { coefLabel, height, moonDisc, todayIndex } from "./format";

describe("station formatting", () => {
  it("prints heights in metres or feet", () => {
    expect(height(1.234, "m")).toBe("1.23 m");
    expect(height(-0.5, "m")).toBe("−0.50 m");
    expect(height(1, "ft")).toBe("3.3 ft");
  });

  it("labels the coefficient", () => {
    expect(coefLabel(30)).toBe("Low");
    expect(coefLabel(45)).toBe("Average");
    expect(coefLabel(70)).toBe("High");
    expect(coefLabel(90)).toBe("Very high");
    expect(coefLabel(null)).toBe("");
  });

  it("shades the moon disc from its illumination and side", () => {
    expect(moonDisc(52, 268)).toEqual({ lit: 52, side: "left" }); // waning: lit on the left
    expect(moonDisc(17, 48)).toEqual({ lit: 17, side: "right" });
  });

  it("finds the station's local today in the month", () => {
    const days = [{ date: "2026-11-14" }, { date: "2026-11-15" }];
    // 2026-11-15 02:00 UTC is still the 14th in New York
    expect(todayIndex(days, "America/New_York", new Date("2026-11-15T02:00:00Z"))).toBe(0);
    expect(todayIndex(days, "America/New_York", new Date("2026-11-15T12:00:00Z"))).toBe(1);
    expect(todayIndex(days, "America/New_York", new Date("2026-12-15T12:00:00Z"))).toBe(-1);
  });
});
