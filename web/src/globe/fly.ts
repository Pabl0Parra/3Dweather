// "Biggest waves": find the highest sea cell and fly the camera there.
import { decodeHeight } from "./codecs";
import type { LandGrid } from "./field";
import type { GlobeManifest } from "./manifest";
import { clampView, wrapLon, type View } from "./view";

export const FLY_MS = 1400;
export const FLY_ZOOM = 3.2;

type Grid = Pick<GlobeManifest, "w" | "h" | "west" | "dlon" | "north" | "dlat">;

/** Highest height byte over sea cells; ties go to the first in row order. */
export function biggestWave(pixels: Uint8ClampedArray, m: Grid, land: LandGrid): { lat: number; lon: number; heightM: number } {
  let best = -1, bx = 0, by = 0;
  for (let y = 0; y < m.h; y++) {
    const lat = m.north - y * m.dlat;
    for (let x = 0; x < m.w; x++) {
      const b = pixels[(y * m.w + x) * 4];
      if (b <= best) continue;
      if (land.isLand(lat, m.west + x * m.dlon)) continue;
      best = b; bx = x; by = y;
    }
  }
  return { lat: m.north - by * m.dlat, lon: wrapLon(m.west + bx * m.dlon), heightM: decodeHeight(Math.max(0, best)) };
}

export function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}

/** Camera part-way along a flight: eased, the short way round, zoom geometric. */
export function flyView(from: View, to: View, t: number): View {
  if (t <= 0) return clampView(from);
  if (t >= 1) return clampView(to);
  const e = easeInOutCubic(t);
  const dLon = ((((to.lon0 - from.lon0) % 360) + 540) % 360) - 180;
  return clampView({
    lat0: from.lat0 + (to.lat0 - from.lat0) * e,
    lon0: from.lon0 + dLon * e,
    zoom: from.zoom * (to.zoom / from.zoom) ** e,
  });
}

/** Where a manifest peak series puts the extreme at an hour (clamped to the series). */
export function peakAt(m: { peaks: Record<string, [number, number, number][]> }, key: string, hour: number): { lat: number; lon: number } | null {
  const series = m.peaks[key];
  if (!series?.length) return null;
  const [, lat, lon] = series[Math.max(0, Math.min(series.length - 1, Math.round(hour)))];
  return { lat, lon };
}
