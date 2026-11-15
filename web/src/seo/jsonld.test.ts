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
