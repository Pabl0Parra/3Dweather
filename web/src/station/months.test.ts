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

describe("a day from the tide table (visitor's today outside the embedded month)", () => {
  it("finds local midnight across a DST change", async () => {
    const { localMidnight } = await import("./format");
    expect(new Date(localMidnight("America/New_York", "2026-12-01")).toISOString()).toBe("2026-12-01T05:00:00.000Z");
    expect(new Date(localMidnight("America/New_York", "2026-07-01")).toISOString()).toBe("2026-07-01T04:00:00.000Z");
    expect(new Date(localMidnight("Pacific/Auckland", "2026-12-01")).toISOString()).toBe("2026-11-30T11:00:00.000Z");
  });

  it("gives the day's turns, its length and its neighbours in minutes from its midnight", async () => {
    const { dayFromTable } = await import("./months");
    const from = Date.UTC(2026, 10, 1);
    const at = (iso: string) => Math.round((Date.parse(iso) - from) / 60000);
    const t: TideTable = { ...table, from: "2026-11-01T00:00:00Z", to: "2027-01-01T00:00:00Z",
      turns: [[at("2026-11-01T03:00:00Z"), 100, 1], [at("2026-11-01T09:00:00Z"), -100, 0], [at("2026-11-01T15:00:00Z"), 90, 1]] };
    const d = dayFromTable(t, "2026-11-01", "America/New_York");
    expect(d.day_minutes).toBe(1500); // clocks go back
    expect(d.tides).toEqual([["04:00", 300, -1, 0], ["10:00", 660, 0.9, 1]]); // 23:00 is the day before
    expect(d.around.map((x) => x[1])).toEqual([-60, 300, 660]);
  });
});
