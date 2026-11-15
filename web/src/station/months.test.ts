import { describe, expect, it } from "vitest";
import { monthTurns, monthsIn, toCsv, type TideTable } from "./months";

const table: TideTable = {
  v: 1, id: "n1", source: "NOAA", donor: null, datum: "MSL",
  from: "2025-11-01T00:00:00Z", to: "2027-11-01T00:00:00Z",
  // 2026-10-31 23:30 local NY = 2026-11-01T03:30Z; 2026-11-01 01:30 EST (after the change) = 06:30Z
  turns: [[Math.round((Date.UTC(2026, 10, 1, 3, 30) - Date.UTC(2025, 10, 1)) / 60000), 120, 1],
          [Math.round((Date.UTC(2026, 10, 1, 6, 30) - Date.UTC(2025, 10, 1)) / 60000), -80, 0]],
};

describe("other months", () => {
  it("lists the months of the file", () => {
    const m = monthsIn(table, "America/New_York");
    expect(m[0]).toBe("2025-10");
    expect(m).toContain("2026-11");
    expect(m[m.length - 1]).toBe("2027-10");
  });

  it("puts each turn on its local day and time", () => {
    expect(monthTurns(table, "2026-10", "America/New_York")).toEqual([{ date: "2026-10-31", hm: "23:30", h: 1.2, hi: true }]);
    expect(monthTurns(table, "2026-11", "America/New_York")).toEqual([{ date: "2026-11-01", hm: "01:30", h: -0.8, hi: false }]);
  });

  it("writes a CSV with a header row", () => {
    const rows = [{ date: "2026-11-01", hm: "01:30", h: -0.8, hi: false }];
    expect(toCsv(rows, "m")).toBe("date,time,tide,height_m\n2026-11-01,01:30,low,-0.80\n");
    expect(toCsv(rows, "ft")).toBe("date,time,tide,height_ft\n2026-11-01,01:30,low,-2.6\n");
  });
});
