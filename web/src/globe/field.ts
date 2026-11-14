// CPU-side reads of the wave layer and the land mask (particles, probe, peak search).
import { decodeHeight, decodeWave } from "./codecs";
import type { GlobeManifest } from "./manifest";

export type WaveSample = { heightM: number; periodS: number; fromDeg: number; u: number; v: number };

type Grid = Pick<GlobeManifest, "w" | "h" | "west" | "dlon" | "north" | "dlat">;

/** Bilinear weights and indices for a point: x wrapped, y clamped. */
function corners(m: Grid, lat: number, lon: number) {
  let fx = (lon - m.west) / m.dlon;
  fx = ((fx % m.w) + m.w) % m.w;
  const fy = Math.max(0, Math.min(m.h - 1, (m.north - lat) / m.dlat));
  const x0 = Math.floor(fx), y0 = Math.floor(fy);
  const x1 = (x0 + 1) % m.w, y1 = Math.min(y0 + 1, m.h - 1);
  const tx = fx - x0, ty = fy - y0;
  return {
    i: [(y0 * m.w + x0) * 4, (y0 * m.w + x1) * 4, (y1 * m.w + x0) * 4, (y1 * m.w + x1) * 4],
    w: [(1 - tx) * (1 - ty), tx * (1 - ty), (1 - tx) * ty, tx * ty],
  };
}

function bilinear(px: Uint8ClampedArray, c: ReturnType<typeof corners>, ch: number): number {
  return px[c.i[0] + ch] * c.w[0] + px[c.i[1] + ch] * c.w[1] + px[c.i[2] + ch] * c.w[2] + px[c.i[3] + ch] * c.w[3];
}

/** Wave conditions at a point: raw bytes interpolated in space and time, then decoded. */
export function sampleWave(a: Uint8ClampedArray, b: Uint8ClampedArray, mix: number, m: Grid, lat: number, lon: number): WaveSample {
  const c = corners(m, lat, lon);
  const at = (ch: number) => bilinear(a, c, ch) * (1 - mix) + bilinear(b, c, ch) * mix;
  const r = at(0), g = at(1), bb = at(2);
  const { periodS, fromDeg } = decodeWave(g, bb);
  return { heightM: decodeHeight(r), periodS, fromDeg, u: (g - 128) / 127, v: (bb - 128) / 127 };
}

/** Equirectangular land mask on the CPU; lon -180 is the left pixel edge, R >= 128 is land. */
export class LandGrid {
  private stride: number;
  constructor(private data: Uint8ClampedArray | Uint8Array, private w: number, private h: number) {
    this.stride = data.length / (w * h); // 4 for RGBA, 1 for a single channel
  }

  isLand(lat: number, lon: number): boolean {
    let x = Math.floor(((lon + 180) / 360) * this.w);
    x = ((x % this.w) + this.w) % this.w;
    const y = Math.max(0, Math.min(this.h - 1, Math.floor(((90 - lat) / 180) * this.h)));
    return this.data[(y * this.w + x) * this.stride] >= 128;
  }
}

/** Browser only: downsample the land mask image into a LandGrid. */
export function landGridFrom(img: ImageBitmap, w = 512, h = 256): LandGrid {
  const canvas = new OffscreenCanvas(w, h);
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(img, 0, 0, w, h);
  return new LandGrid(ctx.getImageData(0, 0, w, h).data, w, h);
}
