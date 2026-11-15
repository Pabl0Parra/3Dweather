import { describe, expect, it } from "vitest";
import { jsonScript } from "./jsonld";

describe("JSON-LD", () => {
  it("escapes what could end the script element, and stays valid JSON", () => {
    const obj = { name: `Fish & "Chips" </script><b>`, sep: "a\u2028b" };
    const s = jsonScript(obj);
    expect(s).not.toMatch(/<\/script/i);
    expect(s).not.toContain("<");
    expect(s).not.toContain("\u2028");
    expect(JSON.parse(s)).toEqual(obj);
  });
});

describe("station FAQ", () => {
  it("answers from the station's own facts and becomes FAQPage JSON-LD", async () => {
    const { faqJsonLd, stationFaq } = await import("./jsonld");
    const faq = stationFaq("Fish & Chips Bay", "Europe/London", "EOT20 global tide model", null);
    expect(faq.length).toBeGreaterThanOrEqual(3);
    expect(faq[0].a).toContain("EOT20");
    expect(faq.some((x) => x.a.includes("Europe/London"))).toBe(true);
    expect(faq.some((x) => /not .*official/.test(x.a))).toBe(true);
    const none = stationFaq("Dry", "UTC", null, null);
    expect(none[0].a).toMatch(/no tide predictions/i);
    const ld = faqJsonLd(faq) as { "@type": string; mainEntity: { name: string; acceptedAnswer: { text: string } }[] };
    expect(ld["@type"]).toBe("FAQPage");
    expect(ld.mainEntity[0].name).toBe(faq[0].q);
    expect(ld.mainEntity[0].acceptedAnswer.text).toBe(faq[0].a);
  });
});
