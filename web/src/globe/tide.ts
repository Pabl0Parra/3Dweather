// Tide height from the 8-constituent atlas: h = sum f·A·cos(V+u − G).
// The atlas stores X = A·cos G and Y = A·sin G per constituent (bytes scaled by amax),
// so A·cos(φ − G) = X·cos φ + Y·sin φ with φ = V + u at the moment asked for.

export type TideAtlas = {
  source: string;
  cons: string[];
  w: number;
  h: number;
  tiles: number;
  west: number;
  north: number;
  dlon: number;
  dlat: number;
  amax: Record<string, number>;
  start: string;
  speed: number[]; // rad per hour
  months: number[][]; // per month: f, V+u (rad) for each constituent
  /** RGBA pixels of the w × (h·tiles) atlas image. */
  pixels: Uint8ClampedArray;
};

export const MASK_CHANNEL = 16;

/** c_k = amax_k·f_k·cos φ_k and s_k = amax_k·f_k·sin φ_k at time t. */
export function phasesAt(a: TideAtlas, t: Date): { c: number[]; s: number[] } {
  const start = new Date(a.start);
  const y0 = start.getUTCFullYear(), m0 = start.getUTCMonth();
  let m = (t.getUTCFullYear() - y0) * 12 + (t.getUTCMonth() - m0);
  m = Math.max(0, Math.min(a.months.length - 1, m)); // clamp outside the table
  const monthStart = Date.UTC(y0, m0 + m, 1);
  const dt = (t.getTime() - monthStart) / 3.6e6;
  const row = a.months[m];
  const c: number[] = [], s: number[] = [];
  a.cons.forEach((name, k) => {
    const amp = a.amax[name] * row[2 * k];
    const phi = row[2 * k + 1] + a.speed[k] * dt;
    c.push(amp * Math.cos(phi));
    s.push(amp * Math.sin(phi));
  });
  return { c, s };
}

/** Bilinear read of atlas channels at a point: x wraps, y clamps. */
export function sampleAtlas(a: TideAtlas, lat: number, lon: number, channels: number[]): number[] {
  let fx = (lon - a.west) / a.dlon;
  fx = ((fx % a.w) + a.w) % a.w;
  const fy = Math.max(0, Math.min(a.h - 1, (a.north - lat) / a.dlat));
  const x0 = Math.floor(fx), y0 = Math.floor(fy);
  const x1 = (x0 + 1) % a.w, y1 = Math.min(y0 + 1, a.h - 1);
  const tx = fx - x0, ty = fy - y0;
  return channels.map((ch) => {
    const tile = Math.floor(ch / 3), comp = ch % 3;
    const at = (x: number, y: number) => a.pixels[((tile * a.h + y) * a.w + x) * 4 + comp];
    return (at(x0, y0) * (1 - tx) + at(x1, y0) * tx) * (1 - ty) + (at(x0, y1) * (1 - tx) + at(x1, y1) * tx) * ty;
  });
}

function heightWith(a: TideAtlas, xy: number[], p: { c: number[]; s: number[] }): number {
  let h = 0;
  for (let k = 0; k < a.cons.length; k++) h += ((xy[2 * k] - 128) / 127) * p.c[k] + ((xy[2 * k + 1] - 128) / 127) * p.s[k];
  return h;
}

/** Tide height (m) and whether it is rising; null where the atlas has no sea. */
export function tideAt(a: TideAtlas, lat: number, lon: number, t: Date): { heightM: number; rising: boolean } | null {
  // The mask is read at the nearest cell, so coasts don't blend sea and land.
  let x = Math.round((lon - a.west) / a.dlon);
  x = ((x % a.w) + a.w) % a.w;
  const y = Math.max(0, Math.min(a.h - 1, Math.round((a.north - lat) / a.dlat)));
  const maskTile = Math.floor(MASK_CHANNEL / 3), maskComp = MASK_CHANNEL % 3;
  if (a.pixels[((maskTile * a.h + y) * a.w + x) * 4 + maskComp] < 128) return null;
  const xy = sampleAtlas(a, lat, lon, Array.from({ length: 2 * a.cons.length }, (_, i) => i));
  const now = heightWith(a, xy, phasesAt(a, t));
  const later = heightWith(a, xy, phasesAt(a, new Date(t.getTime() + 600_000)));
  return { heightM: now, rising: later > now };
}

/** Browser: load tide.json and decode tide.png without colour conversion. */
export async function loadTideAtlas(base: string): Promise<TideAtlas> {
  const [meta, img] = await Promise.all([
    fetch(`${base}/tide.json`).then((r) => { if (!r.ok) throw new Error(`tide.json: HTTP ${r.status}`); return r.json(); }),
    fetch(`${base}/tide.png`).then((r) => { if (!r.ok) throw new Error(`tide.png: HTTP ${r.status}`); return r.blob(); }),
  ]);
  const bitmap = await createImageBitmap(img, { colorSpaceConversion: "none", premultiplyAlpha: "none" });
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();
  return { ...meta, pixels: ctx.getImageData(0, 0, canvas.width, canvas.height).data };
}
