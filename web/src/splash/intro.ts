// Ignition timing: what the globe shows at each moment of the 3 s opening.

export type Intro = { arrival: number; body: number; coast: number; zoom: number };

export const INTRO_S = 3.0;
export const HOLD_S = 2.45; // waits here if the forecast is not ready yet
const START_ZOOM = 0.82;
const KEY = "3dw.splash";

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
const ramp = (t: number, a: number, b: number) => clamp01((t - a) / (b - a));
const easeOut = (x: number) => 1 - (1 - x) ** 3;
const easeInOut = (x: number) => (x < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2);

export function introAt(t: number): Intro {
  if (t >= INTRO_S) return { arrival: 1, body: 1, coast: 1, zoom: 1 };
  return {
    arrival: easeOut(ramp(t, 0.55, 1.3)),
    body: easeOut(ramp(t, 0.9, 1.4)),
    coast: ramp(t, 1.35, 1.95),
    zoom: START_ZOOM + (1 - START_ZOOM) * easeInOut(ramp(t, HOLD_S, INTRO_S)),
  };
}

export function shouldPlay(search: string, store: Storage | null): boolean {
  if (new URLSearchParams(search).has("nosplash")) return false;
  try {
    return store?.getItem(KEY) !== "1";
  } catch {
    return true;
  }
}

export function markPlayed(store: Storage | null): void {
  try { store?.setItem(KEY, "1"); } catch { /* blocked: plays again next load */ }
}

const GLYPHS = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#%&*+<>/";

/** Text resolving left to right out of random glyphs; spaces stay spaces. */
export function scramble(target: string, progress: number, rand: () => number): string {
  const done = Math.floor(clamp01(progress) * target.length + 1e-9);
  let out = target.slice(0, done);
  for (let i = done; i < target.length; i++) {
    out += target[i] === " " ? " " : GLYPHS[Math.floor(rand() * GLYPHS.length)];
  }
  return out;
}
