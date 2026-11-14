// Flat regional map geometry: equirectangular, x scaled by cos(focus latitude).
import type { RegionManifest } from "./sheet";

export type FlatView = { lon0: number; lat0: number; zoom: number };
export type FlatGeom = { m: RegionManifest; w: number; h: number }; // w, h in CSS px

const RAD = Math.PI / 180;
export const MIN_ZOOM = 1;
export const MAX_ZOOM = 8;

export const xScale = (m: RegionManifest): number => Math.cos(((m.focus[1] + m.focus[3]) / 2) * RAD);

/** Pixels per degree of latitude at zoom 1: the focus box just fits. */
export function fitScale(g: FlatGeom): number {
  const [w0, s0, e0, n0] = g.m.focus;
  return Math.min(g.w / ((e0 - w0) * xScale(g.m)), g.h / (n0 - s0));
}

export function initialView(m: RegionManifest): FlatView {
  const [w0, s0, e0, n0] = m.focus;
  return { lon0: (w0 + e0) / 2, lat0: (s0 + n0) / 2, zoom: 1 };
}

export function projectFlat(v: FlatView, g: FlatGeom, lat: number, lon: number): { x: number; y: number } {
  const s = fitScale(g) * v.zoom;
  return { x: g.w / 2 + (lon - v.lon0) * xScale(g.m) * s, y: g.h / 2 - (lat - v.lat0) * s };
}

export function unprojectFlat(v: FlatView, g: FlatGeom, x: number, y: number): { lat: number; lon: number } {
  const s = fitScale(g) * v.zoom;
  return { lat: v.lat0 - (y - g.h / 2) / s, lon: v.lon0 + (x - g.w / 2) / (xScale(g.m) * s) };
}

/** Zoom 1..8; the centre keeps the view inside the grid (or centred on it when the grid is smaller). */
export function clampFlat(v: FlatView, g: FlatGeom): FlatView {
  const zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, v.zoom));
  const s = fitScale(g) * zoom;
  const halfLon = g.w / (2 * xScale(g.m) * s), halfLat = g.h / (2 * s);
  const fit = (c: number, lo: number, hi: number, half: number) =>
    2 * half >= hi - lo ? (lo + hi) / 2 : Math.max(lo + half, Math.min(hi - half, c));
  return { zoom, lon0: fit(v.lon0, g.m.west, g.m.east, halfLon), lat0: fit(v.lat0, g.m.south, g.m.north, halfLat) };
}
