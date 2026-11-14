// Orthographic view of the globe. Screen coordinates are CSS pixels, y down.

export type View = { lat0: number; lon0: number; zoom: number };

export const MIN_ZOOM = 0.75;
export const MAX_ZOOM = 16;
export const MAX_LAT = 85;

const D = Math.PI / 180;

export function wrapLon(lon: number): number {
  return ((((lon + 180) % 360) + 360) % 360) - 180;
}

export function clampView(v: View): View {
  return {
    lat0: Math.max(-MAX_LAT, Math.min(MAX_LAT, v.lat0)),
    lon0: wrapLon(v.lon0),
    zoom: Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, v.zoom)),
  };
}

export function radiusPx(zoom: number, w: number, h: number): number {
  return zoom * 0.45 * Math.min(w - 16, h - 16);
}

export function project(v: View, w: number, h: number, lat: number, lon: number) {
  const r = radiusPx(v.zoom, w, h);
  const p = lat * D, p0 = v.lat0 * D, dl = (lon - v.lon0) * D;
  const cosc = Math.sin(p0) * Math.sin(p) + Math.cos(p0) * Math.cos(p) * Math.cos(dl);
  const x = r * Math.cos(p) * Math.sin(dl);
  const y = r * (Math.cos(p0) * Math.sin(p) - Math.sin(p0) * Math.cos(p) * Math.cos(dl));
  return { x: w / 2 + x, y: h / 2 - y, visible: cosc >= 0 };
}

export function unproject(v: View, w: number, h: number, sx: number, sy: number): { lat: number; lon: number } | null {
  const r = radiusPx(v.zoom, w, h);
  const x = (sx - w / 2) / r, y = (h / 2 - sy) / r;
  const rho = Math.hypot(x, y);
  if (rho > 1) return null;
  if (rho === 0) return { lat: v.lat0, lon: v.lon0 };
  const c = Math.asin(rho), p0 = v.lat0 * D;
  const lat = Math.asin(Math.cos(c) * Math.sin(p0) + (y * Math.sin(c) * Math.cos(p0)) / rho);
  const lon = v.lon0 * D + Math.atan2(x * Math.sin(c), rho * Math.cos(p0) * Math.cos(c) - y * Math.sin(p0) * Math.sin(c));
  return { lat: lat / D, lon: wrapLon(lon / D) };
}

/** Drag by a screen offset: the surface follows the pointer. */
export function rotateBy(v: View, dxPx: number, dyPx: number, w: number, h: number): View {
  const r = radiusPx(v.zoom, w, h);
  return clampView({ lat0: v.lat0 + (dyPx / r) / D, lon0: v.lon0 - (dxPx / r) / D, zoom: v.zoom });
}
