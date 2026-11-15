import { describe, expect, it } from "vitest";
import { nearItems } from "./near";

describe("tides near you", () => {
  it("lists the nearest places with distances", () => {
    const items = nearItems([
      { name: "A", path: "us/x/a", km: 3.24, region: "X", cc: "US" },
      { name: "B", path: "us/x/b", km: 41.6, region: "X", cc: "US" },
    ] as never);
    expect(items).toEqual([
      { name: "A", href: "/us/x/a", detail: "X · 3.2 km" },
      { name: "B", href: "/us/x/b", detail: "X · 42 km" },
    ]);
  });
});
