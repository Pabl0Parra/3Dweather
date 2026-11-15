// Formatting shared by the station page's build-time HTML and its browser script.

export type Unit = "m" | "ft";
export type Hm = [string, number] | null; // ["HH:MM", minutes since local midnight]
export type Turn = [string, number, number, 0 | 1]; // ["HH:MM", minutes, height m, 1 high]

export type StationDay = {
  date: string; day_minutes: number; sunrise: Hm; sunset: Hm; transit: Hm; dawn: Hm; dusk: Hm;
  golden: [Hm, Hm][]; blue: [Hm, Hm][]; day_length_h: number;
  moon: { phase_angle: number; illum: number; name: string; rise: Hm; set: Hm; transit: Hm; distance_km: number };
  solunar: { major: [Hm, Hm][]; minor: [Hm, Hm][] };
  coef: number | null; tides: Turn[];
};

export type StationData = {
  v: 1; id: string; tz: string; today: string; has_tides: boolean; source: string | null;
  donor: { name: string; path: string } | null; days: StationDay[];
  curve: { from: string; step_min: number; days: number[]; cm: (number | null)[] } | null;
};

const FT = 3.28084;
const minus = (s: string) => s.replace("-", "−");

export function height(m: number, unit: Unit): string {
  return unit === "ft" ? `${minus((m * FT).toFixed(1))} ft` : `${minus(m.toFixed(2))} m`;
}

export function coefLabel(c: number | null): string {
  if (c == null) return "";
  return c < 45 ? "Low" : c < 70 ? "Average" : c < 90 ? "High" : "Very high";
}

/** Percent lit and which side is lit (northern-hemisphere view): waxing right, waning left. */
export function moonDisc(illum: number, phaseAngle: number): { lit: number; side: "left" | "right" } {
  return { lit: illum, side: phaseAngle % 360 < 180 ? "right" : "left" };
}

/** The station's local date for `now` as YYYY-MM-DD. */
export function localDate(tz: string, now: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

/** Index of the station's local today in `days`, or -1 when the month does not hold it. */
export function todayIndex(days: { date: string }[], tz: string, now: Date): number {
  const d = localDate(tz, now);
  return days.findIndex((x) => x.date === d);
}

export function dayLabel(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })
    .format(new Date(Date.UTC(y, m - 1, d)));
}

function offsetMinutes(tz: string, t: number): number {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", {
    timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(t)).map((x) => [x.type, x.value]));
  const wall = Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day), Number(p.hour) % 24, Number(p.minute));
  return Math.round((wall - Math.floor(t / 60000) * 60000) / 60000);
}

/** The instant (ms) of local midnight starting `date` (YYYY-MM-DD) in `tz`. */
export function localMidnight(tz: string, date: string): number {
  const [y, m, d] = date.split("-").map(Number);
  const guess = Date.UTC(y, m - 1, d);
  const first = guess - offsetMinutes(tz, guess) * 60000;
  return guess - offsetMinutes(tz, first) * 60000;
}

export function addDays(date: string, n: number): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

const span = (p: [Hm, Hm]) => `${p[0] ? p[0][0] : "–"}–${p[1] ? p[1][0] : "–"}`;

/** The "Sun and moon" facts for one day, as printed (build time and browser alike). */
export function skyFacts(d: StationDay): Record<string, string> {
  const t = (x: Hm) => (x ? x[0] : "–");
  return {
    sunrise: t(d.sunrise), sunset: t(d.sunset), daylight: `${d.day_length_h.toFixed(1)} h`,
    moon: `${d.moon.name}, ${d.moon.illum}% lit`, moonrise: t(d.moon.rise), moonset: t(d.moon.set),
    coef: d.coef == null ? "–" : `${d.coef} · ${coefLabel(d.coef)}`,
    major: d.solunar.major.map(span).join(", ") || "–", minor: d.solunar.minor.map(span).join(", ") || "–",
    golden: d.golden.map(span).join(", ") || "–",
  };
}
