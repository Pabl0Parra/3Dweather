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
