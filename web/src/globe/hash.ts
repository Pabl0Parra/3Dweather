// Deep links: #lat,lon,zoom
import { clampView, type View } from "./view";

export function parseHash(hash: string): View | null {
  const parts = hash.replace(/^#/, "").split(",");
  if (parts.length !== 3 || parts.some((p) => p.trim() === "")) return null;
  const [lat0, lon0, zoom] = parts.map(Number);
  if (![lat0, lon0, zoom].every(Number.isFinite)) return null;
  return clampView({ lat0, lon0, zoom });
}

export function formatHash(v: View): string {
  return `#${v.lat0.toFixed(2)},${v.lon0.toFixed(2)},${v.zoom.toFixed(1)}`;
}
