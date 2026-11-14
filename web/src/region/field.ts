// Values and colours from the regional sheets: bilinear in space, linear in time.
import { decodeCloud, decodeRain, decodeWind } from "../globe/codecs";
import type { Sample } from "../globe/field";
import { rampTable, type Layer } from "../globe/layers";
import { frameCount, sheetIndex, type RegionManifest, type Sheet } from "./sheet";

const CLOUD: [number, number, number] = [222, 230, 240];
const VEIL = 0.55; // cloud opacity at 100 %, as on the globe

function frames(m: RegionManifest, hour: number): { f0: number; f1: number; t: number } {
  const n = frameCount(m);
  const h = Math.max(0, Math.min(n - 1, hour));
  const f0 = Math.floor(h);
  return { f0, f1: Math.min(f0 + 1, n - 1), t: h - f0 };
}

/** Bytes of one channel at a point, or null outside the grid. */
function reader(m: RegionManifest, lat: number, lon: number) {
  const fx = ((lon - m.west) / (m.east - m.west)) * (m.w - 1);
  const fy = ((m.north - lat) / (m.north - m.south)) * (m.h - 1);
  if (!(fx >= 0 && fx <= m.w - 1 && fy >= 0 && fy <= m.h - 1)) return null;
  const x0 = Math.floor(fx), y0 = Math.floor(fy);
  const x1 = Math.min(x0 + 1, m.w - 1), y1 = Math.min(y0 + 1, m.h - 1);
  const tx = fx - x0, ty = fy - y0;
  return (s: Sheet, j: number, ch: number) => {
    const at = (x: number, y: number) => s.pixels[sheetIndex(m, s.width, j, x, y) + ch];
    return (at(x0, y0) * (1 - tx) + at(x1, y0) * tx) * (1 - ty) + (at(x0, y1) * (1 - tx) + at(x1, y1) * tx) * ty;
  };
}

/** Wind, rain and cloud at a point and (fractional) hour; null outside the grid. */
export function sampleRegion(a: Sheet, b: Sheet, m: RegionManifest, hour: number, lat: number, lon: number): Sample | null {
  const read = reader(m, lat, lon);
  if (!read) return null;
  const { f0, f1, t } = frames(m, hour);
  const at = (s: Sheet, ch: number) => read(s, f0, ch) * (1 - t) + read(s, f1, ch) * t;
  const u = decodeWind(at(a, 0)), v = decodeWind(at(a, 1));
  return {
    windMs: Math.hypot(u, v),
    windFromDeg: ((Math.atan2(-u, -v) * 180) / Math.PI + 360) % 360,
    rainMmh: decodeRain(at(a, 2)),
    cloudPct: decodeCloud(at(b, 0)),
  };
}

/** Wind (m/s, x east, y north) at a point and hour, for the particles; null outside the grid. */
export function windAt(a: Sheet, m: RegionManifest, hour: number, lat: number, lon: number): { u: number; v: number } | null {
  const read = reader(m, lat, lon);
  if (!read) return null;
  const { f0, f1, t } = frames(m, hour);
  return {
    u: decodeWind(read(a, f0, 0) * (1 - t) + read(a, f1, 0) * t),
    v: decodeWind(read(a, f0, 1) * (1 - t) + read(a, f1, 1) * t),
  };
}

const tables = new Map<string, Uint8Array>();
const tableFor = (l: Layer) => {
  let t = tables.get(l.id);
  if (!t) tables.set(l.id, (t = rampTable(l)));
  return t;
};

/** RGBA at grid resolution (w × h) for the rain layer (rain over a cloud veil) or the wind layer. */
export function fieldPixels(a: Sheet, b: Sheet, m: RegionManifest, hour: number, layer: Layer): Uint8ClampedArray<ArrayBuffer> {
  const out = new Uint8ClampedArray(m.w * m.h * 4);
  const { f0, f1, t } = frames(m, hour);
  const table = tableFor(layer);
  const wind = layer.shade.kind === "vector";
  const vecMax = layer.vecMax ?? 1;
  for (let y = 0; y < m.h; y++)
    for (let x = 0; x < m.w; x++) {
      const i0 = sheetIndex(m, a.width, f0, x, y), i1 = sheetIndex(m, a.width, f1, x, y);
      const ch = (s: Sheet, c: number) => s.pixels[i0 + c] * (1 - t) + s.pixels[i1 + c] * t;
      const o = (y * m.w + x) * 4;
      if (wind) {
        const speed = Math.hypot(decodeWind(ch(a, 0)), decodeWind(ch(a, 1)));
        const k = Math.round(Math.sqrt(Math.min(1, speed / vecMax)) * 255) * 4;
        out.set(table.subarray(k, k + 4), o);
        continue;
      }
      const av = (decodeCloud(ch(b, 0)) / 100) * VEIL;
      const k = Math.round(ch(a, 2)) * 4;
      const ar = table[k + 3] / 255;
      const oa = ar + av * (1 - ar);
      if (oa <= 0) continue;
      for (let c = 0; c < 3; c++) out[o + c] = (table[k + c] * ar + CLOUD[c] * av * (1 - ar)) / oa;
      out[o + 3] = oa * 255;
    }
  return out;
}
