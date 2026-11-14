import { expect, test } from "vitest";
import { INTRO_S, introAt, markPlayed, scramble, shouldPlay } from "./intro";

function fakeStorage(init: Record<string, string>): Storage {
  const m = new Map(Object.entries(init));
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) } as unknown as Storage;
}
const throwingStorage = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } } as unknown as Storage;

test("intro timing", () => {
  expect(INTRO_S).toBe(3);
  expect(introAt(0)).toEqual({ arrival: 0, body: 0, coast: 0, zoom: 0.82 });
  expect(introAt(1.35).coast).toBe(0);
  expect(introAt(1.95).coast).toBeCloseTo(1);
  expect(introAt(2.45).zoom).toBeCloseTo(0.82);
  expect(introAt(0.9).body).toBe(0);
  expect(introAt(1.4).body).toBeCloseTo(1);
  expect(introAt(0.55).arrival).toBe(0);
  expect(introAt(1.3).arrival).toBeCloseTo(1);
  expect(introAt(3)).toEqual({ arrival: 1, body: 1, coast: 1, zoom: 1 });
  expect(introAt(99)).toEqual({ arrival: 1, body: 1, coast: 1, zoom: 1 });
});

test("values only grow", () => {
  let prev = introAt(0);
  for (let t = 0.05; t <= 3; t += 0.05) {
    const s = introAt(t);
    for (const k of ["arrival", "body", "coast", "zoom"] as const) expect(s[k]).toBeGreaterThanOrEqual(prev[k] - 1e-9);
    prev = s;
  }
});

test("plays once per session, never with nosplash", () => {
  const s = fakeStorage({});
  expect(shouldPlay("", s)).toBe(true);
  markPlayed(s);
  expect(shouldPlay("", s)).toBe(false);
  expect(shouldPlay("?nosplash", fakeStorage({}))).toBe(false);
  expect(shouldPlay("?debug&nosplash", fakeStorage({}))).toBe(false);
  expect(shouldPlay("", throwingStorage)).toBe(true);
  expect(() => markPlayed(throwingStorage)).not.toThrow();
  expect(shouldPlay("", null)).toBe(true);
});

test("scramble resolves left to right", () => {
  expect(scramble("ABC", 1, Math.random)).toBe("ABC");
  expect(scramble("ABC", 1 / 3, () => 0)[0]).toBe("A");
  expect(scramble("ABC", 0, () => 0)).toHaveLength(3);
  expect(scramble("A B", 0, () => 0)[1]).toBe(" "); // spaces stay spaces
});
