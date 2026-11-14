// Wave height colour scale (our own), from deep navy to the splash's hot pink.
import { decodeHeight } from "./codecs";

export type Rgba = [number, number, number, number];

export const RAMP_STOPS: [number, Rgba][] = [
  [0, [12, 40, 80, 115]],
  [1, [20, 90, 150, 153]],
  [2, [30, 150, 190, 184]],
  [3, [60, 200, 170, 204]],
  [4.5, [220, 215, 90, 217]],
  [6, [245, 150, 50, 230]],
  [9, [230, 60, 70, 237]],
  [12, [255, 79, 163, 242]],
  [16, [245, 235, 255, 247]],
];

export const LEGEND_TICKS = [1, 3, 6, 9, 12];

export function colourAt(m: number): Rgba {
  if (m <= RAMP_STOPS[0][0]) return [...RAMP_STOPS[0][1]] as Rgba;
  for (let i = 1; i < RAMP_STOPS.length; i++) {
    const [m1, c1] = RAMP_STOPS[i];
    if (m <= m1) {
      const [m0, c0] = RAMP_STOPS[i - 1];
      const t = (m - m0) / (m1 - m0);
      return c0.map((c, k) => Math.round(c + (c1[k] - c) * t)) as Rgba;
    }
  }
  return [...RAMP_STOPS[RAMP_STOPS.length - 1][1]] as Rgba;
}

/** 256 RGBA entries indexed by the height byte, for a 256x1 lookup texture. */
export function rampTable(): Uint8Array {
  const t = new Uint8Array(256 * 4);
  for (let i = 0; i < 256; i++) t.set(colourAt(decodeHeight(i)), i * 4);
  return t;
}
