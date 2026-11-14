// "The next three days": the strongest wind and heaviest rain anywhere on the map.
import { formatRain, formatSpeed, type Units } from "../globe/units";
import type { RegionManifest } from "./sheet";

export type PeakLine = { value: string; when: string; where: string; lat: number; lon: number; hour: number };

const R_KM = 6371;
const RAD = Math.PI / 180;

function km(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const a = Math.sin(((lat2 - lat1) * RAD) / 2) ** 2
    + Math.cos(lat1 * RAD) * Math.cos(lat2 * RAD) * Math.sin(((lon2 - lon1) * RAD) / 2) ** 2;
  return 2 * R_KM * Math.asin(Math.sqrt(a));
}

export function nearestCity(m: RegionManifest, lat: number, lon: number): { name: string; km: number } {
  let best = { name: "", km: Infinity };
  for (const [name, la, lo] of m.cities) {
    const d = km(lat, lon, la, lo);
    if (d < best.km) best = { name, km: d };
  }
  return best;
}

/** "Sat 14 Nov, 09:00" in the given zone. */
export function localTime(t: Date, timeZone: string): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", { timeZone, weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
      .formatToParts(t).map((p) => [p.type, p.value]),
  );
  return `${parts.weekday} ${parts.day} ${parts.month}, ${parts.hour}:${parts.minute}`;
}

function line(m: RegionManifest, series: number[][], value: (v: number) => string): PeakLine {
  let h = 0;
  series.forEach((p, i) => { if (p[0] > series[h][0]) h = i; });
  const [v, lat, lon] = series[h];
  const near = nearestCity(m, lat, lon);
  const where = near.km < 15 ? `near ${near.name}` : `about ${Math.round(near.km / 10) * 10 || Math.round(near.km)} km from ${near.name}`;
  return { value: value(v), when: localTime(new Date(Date.parse(m.run) + h * 3.6e6), m.tz), where, lat, lon, hour: h };
}

export function peakSummary(m: RegionManifest, u: Units): { wind: PeakLine; rain: PeakLine } {
  return {
    wind: line(m, m.peaks.wind, (v) => formatSpeed(v, u.speed)),
    rain: line(m, m.peaks.rain, (v) => formatRain(v, u.length)),
  };
}
