import { describe, expect, it } from "vitest";
import { embedUrl, iframeSnippet, parseParams } from "./params";

describe("widget options", () => {
  it("parses with defaults and clamps", () => {
    expect(parseParams("?station=us/new-york/new-york-city")).toEqual({ station: "us/new-york/new-york-city", unit: "m", theme: "dark", days: 1 });
    expect(parseParams("?station=fr/bretagne/brest&unit=ft&theme=light&days=3")).toMatchObject({ unit: "ft", theme: "light", days: 3 });
    expect(parseParams("?station=fr/bretagne/brest&unit=yards&theme=pink&days=9")).toMatchObject({ unit: "m", theme: "dark", days: 3 });
    expect(parseParams("?station=fr/bretagne/brest&days=0").days).toBe(1);
  });

  it("rejects station values that are not a catalogue path", () => {
    for (const bad of ["../x/y", "a/b", "http://evil.test/a/b", "us/NY/x", "us/ny/x/y", "us//x", ""]) {
      expect(parseParams(`?station=${encodeURIComponent(bad)}`).station).toBeNull();
    }
    expect(parseParams("").station).toBeNull();
  });

  it("builds the widget URL and an escaped iframe snippet", () => {
    const opts = { station: "us/new-york/new-york-city", unit: "ft" as const, theme: "light" as const, days: 2 as const };
    expect(embedUrl("https://s.test", opts)).toBe("https://s.test/embed/tide?station=us%2Fnew-york%2Fnew-york-city&unit=ft&theme=light&days=2");
    const html = iframeSnippet("https://s.test", opts, `Bob's "Bay" <x>`);
    expect(html).toMatch(/^<iframe src="https:\/\/s\.test\/embed\/tide\?station=us%2Fnew-york%2Fnew-york-city&amp;unit=ft&amp;theme=light&amp;days=2"/);
    expect(html).toContain('title="Tide times for Bob\'s &quot;Bay&quot; &lt;x&gt;"');
    expect(html).toContain('height="');
    expect(html).not.toContain("<x>");
  });
});
