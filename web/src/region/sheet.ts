// The run's regional files: {region}.json and the 8-column sprite sheets.

export type RegionManifest = {
  region: string;
  run: string;
  hours: number; // frames: hour 0 to hour hours - 1
  cols: number;
  w: number;
  h: number;
  north: number;
  south: number;
  west: number;
  east: number;
  focus: [number, number, number, number]; // west, south, east, north of the opening view
  tz: string;
  place: string;
  cities: [string, number, number][];
  peaks: { wind: number[][]; rain: number[][] }; // per hour: [value, lat, lon]
  masked: boolean;
};

/** Decoded RGBA pixels of a whole sprite sheet. */
export type Sheet = { pixels: Uint8ClampedArray; width: number; height: number };

export const frameCount = (m: RegionManifest): number => m.hours;

/** Byte offset of cell (x, y) of frame j: frames run along rows of m.cols. */
export function sheetIndex(m: RegionManifest, sheetW: number, j: number, x: number, y: number): number {
  const row = Math.floor(j / m.cols), col = j % m.cols;
  return ((row * m.h + y) * sheetW + col * m.w + x) * 4;
}

export async function loadRegionManifest(base: string, dir: string, slug: string): Promise<RegionManifest> {
  const r = await fetch(`${base}/${dir}/${slug}.json`);
  if (!r.ok) throw new Error(`${slug}.json: HTTP ${r.status}`);
  return r.json();
}

/** Browser: a sprite sheet decoded without colour conversion. */
export async function loadSheet(url: string): Promise<Sheet> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  const bmp = await createImageBitmap(await r.blob(), { colorSpaceConversion: "none", premultiplyAlpha: "none" });
  const canvas = new OffscreenCanvas(bmp.width, bmp.height);
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(bmp, 0, 0);
  bmp.close();
  return { pixels: ctx.getImageData(0, 0, canvas.width, canvas.height).data, width: canvas.width, height: canvas.height };
}
