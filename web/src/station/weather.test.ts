import { describe, expect, it } from "vitest";
import { decodeStation, type StationWx } from "./weather";

const file: StationWx = {
  v: 1, run: "2026-11-15T06:00Z", start: "2026-11-15T06:00Z", step_h: 3, n: 2,
  fields: ["t", "ws", "wd", "wh"], scale: { t: 10, ws: 10, wd: 1, wh: 100 },
  stations: { n1: { t: [123, null], ws: [50, 61], wd: [270, 280], wh: [150, 160] } },
};

describe("station weather", () => {
  it("decodes one station's series", () => {
    const w = decodeStation(file, "n1")!;
    expect(w.times.map((d) => d.toISOString())).toEqual(["2026-11-15T06:00:00.000Z", "2026-11-15T09:00:00.000Z"]);
    expect(w.rows[0]).toEqual({ t: 12.3, ws: 5, wd: 270, wh: 1.5 });
    expect(w.rows[1].t).toBeNull();
  });

  it("returns null for a station not in the file", () => {
    expect(decodeStation(file, "nope")).toBeNull();
  });
});
