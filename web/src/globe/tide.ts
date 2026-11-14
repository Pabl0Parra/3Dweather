// Tide height from the 8-constituent atlas: h = sum f·A·cos(V+u − G).
// The atlas stores X = A·cos G and Y = A·sin G per constituent (bytes scaled by amax),
// so A·cos(φ − G) = X·cos φ + Y·sin φ with φ = V + u at the moment asked for.

export type TideAtlas = {
  source: string;
  /** File name of the atlas image, named after its content. */
  png: string;
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
  // Sea-weighted bilinear: land cells hold X = Y = 0 and would pull coastal heights toward 0.
  const chans = Array.from({ length: 2 * a.cons.length }, (_, i) => i);
  const sum = new Array(chans.length).fill(0);
  let fx = (lon - a.west) / a.dlon;
  fx = ((fx % a.w) + a.w) % a.w;
  const fy = Math.max(0, Math.min(a.h - 1, (a.north - lat) / a.dlat));
  const x0 = Math.floor(fx), y0 = Math.floor(fy);
  const tx = fx - x0, ty = fy - y0;
  let seaW = 0;
  for (const [cx, cy, wt] of [[x0, y0, (1 - tx) * (1 - ty)], [x0 + 1, y0, tx * (1 - ty)], [x0, y0 + 1, (1 - tx) * ty], [x0 + 1, y0 + 1, tx * ty]]) {
    const xx = cx % a.w, yy = Math.min(cy, a.h - 1);
    if (a.pixels[((maskTile * a.h + yy) * a.w + xx) * 4 + maskComp] < 128) continue;
    seaW += wt;
    chans.forEach((ch, i) => { sum[i] += wt * (a.pixels[((Math.floor(ch / 3) * a.h + yy) * a.w + xx) * 4 + (ch % 3)] - 128); });
  }
  const xy = sum.map((v) => v / seaW + 128);
  const now = heightWith(a, xy, phasesAt(a, t));
  const later = heightWith(a, xy, phasesAt(a, new Date(t.getTime() + 600_000)));
  return { heightM: now, rising: later > now };
}

/** The sea cell with the highest tide at time t (cell centres, no interpolation). */
export function highestTide(a: TideAtlas, t: Date): { lat: number; lon: number; heightM: number } | null {
  const p = phasesAt(a, t);
  const n = a.cons.length, plane = a.w * a.h;
  const maskBase = Math.floor(MASK_CHANNEL / 3) * plane * 4 + (MASK_CHANNEL % 3);
  let best = -Infinity, bi = -1;
  for (let i = 0; i < plane; i++) {
    if (a.pixels[maskBase + i * 4] < 128) continue;
    let h = 0;
    for (let k = 0; k < n; k++) {
      const cx = 2 * k, cy = cx + 1;
      const x = a.pixels[Math.floor(cx / 3) * plane * 4 + i * 4 + (cx % 3)];
      const y = a.pixels[Math.floor(cy / 3) * plane * 4 + i * 4 + (cy % 3)];
      h += ((x - 128) / 127) * p.c[k] + ((y - 128) / 127) * p.s[k];
    }
    if (h > best) { best = h; bi = i; }
  }
  if (bi < 0) return null;
  const x = bi % a.w, y = Math.floor(bi / a.w);
  return { lat: a.north - y * a.dlat, lon: a.west + x * a.dlon, heightM: best };
}

/** Browser: load tide.json, then the image it names (tide-<hash>.png), decoded without colour conversion. */
export async function loadTideAtlas(base: string): Promise<TideAtlas> {
  const meta = await fetch(`${base}/tide.json`).then((r) => { if (!r.ok) throw new Error(`tide.json: HTTP ${r.status}`); return r.json(); });
  const png: string = meta.png;
  const img = await fetch(`${base}/${png}`).then((r) => { if (!r.ok) throw new Error(`${png}: HTTP ${r.status}`); return r.blob(); });
  const bitmap = await createImageBitmap(img, { colorSpaceConversion: "none", premultiplyAlpha: "none" });
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();
  return { ...meta, pixels: ctx.getImageData(0, 0, canvas.width, canvas.height).data };
}
