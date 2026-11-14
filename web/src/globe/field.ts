// CPU-side reads of the wave layer and the land mask (particles, probe, peak search).
import { decodeAirTemp, decodeCloud, decodeCurrent, decodeGust, decodeHeight, decodeRain, decodeSeaTemp, decodeWave, decodeWind } from "./codecs";
import type { FramePairPixels } from "./frames";
import type { Family, Layer } from "./layers";
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

export type Frames = Partial<Record<Family, FramePairPixels>>;

/** What one point holds, for the families a layer loaded. Absent fields are not known. */
export type Sample = {
  windMs?: number; windFromDeg?: number; gustMs?: number; rainMmh?: number; cloudPct?: number;
  airC?: number; waveM?: number; periodS?: number; waveFromDeg?: number;
  currentMs?: number; currentToDeg?: number; seaC?: number;
};

const toDeg = (rad: number) => ((rad * 180) / Math.PI + 360) % 360;

/** Raw bytes of several channels at a point, interpolated in space and time. */
export function sampleBytes(f: FramePairPixels, m: Grid, lat: number, lon: number, channels: number[]): number[] {
  const c = corners(m, lat, lon);
  return channels.map((ch) => bilinear(f.a, c, ch) * (1 - f.mix) + bilinear(f.b, c, ch) * f.mix);
}

export function sampleLayer(layer: Layer, frames: Frames, m: Grid & { gustHours?: number }, lat: number, lon: number, hour: number): Sample {
  const s: Sample = {};
  if (frames.a) {
    const [u, v, r] = sampleBytes(frames.a, m, lat, lon, [0, 1, 2]).map((b, i) => (i < 2 ? decodeWind(b) : decodeRain(b)));
    s.windMs = Math.hypot(u, v);
    s.windFromDeg = toDeg(Math.atan2(-u, -v));
    s.rainMmh = r;
  }
  if (frames.b) {
    const [cloud, , gust] = sampleBytes(frames.b, m, lat, lon, [0, 1, 2]);
    s.cloudPct = decodeCloud(cloud);
    if (hour <= (m.gustHours ?? 84)) s.gustMs = decodeGust(gust);
  }
  if (frames.t) s.airC = decodeAirTemp(sampleBytes(frames.t, m, lat, lon, [0])[0]);
  if (frames.w) {
    const w = sampleWave(frames.w.a, frames.w.b, frames.w.mix, m, lat, lon);
    s.waveM = w.heightM; s.periodS = w.periodS; s.waveFromDeg = w.fromDeg;
  }
  if (frames.c) {
    const [u, v, sea] = sampleBytes(frames.c, m, lat, lon, [0, 1, 2]);
    const cu = decodeCurrent(u), cv = decodeCurrent(v);
    s.currentMs = Math.hypot(cu, cv);
    s.currentToDeg = toDeg(Math.atan2(cu, cv));
    s.seaC = decodeSeaTemp(sea);
  }
  void layer;
  return s;
}

/** Particle step vector (x east, y north) for a layer, scaled to about 0..1; null without data. */
export function flowVector(layer: Layer, frames: Frames, m: Grid, lat: number, lon: number): { u: number; v: number } | null {
  const f = frames[layer.flow.family];
  if (!f) return null;
  const [bu, bv] = sampleBytes(f, m, lat, lon, layer.flow.channels);
  if (layer.flow.family === "w") return { u: (bu - 128) / 127, v: (bv - 128) / 127 };
  const dec = layer.flow.family === "c" ? decodeCurrent : decodeWind;
  return { u: dec(bu) / layer.flow.scale, v: dec(bv) / layer.flow.scale };
}
