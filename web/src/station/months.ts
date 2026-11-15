// Other months and CSV from the station's 25-month tide table, tides/{path}.json.
import { addDays, localMidnight, type Turn, type Unit } from "./format";

export type TideTable = {
  v: 1; id: string; name?: string; tz?: string; source: string; donor: { name: string; path: string } | string | null; datum: string;
  from: string; to: string; turns: [number, number, 0 | 1][];
};
export type MonthTurn = { date: string; hm: string; h: number; hi: boolean };

const FT = 3.28084;
const fmts = new Map<string, Intl.DateTimeFormat>();

function local(tz: string, t: number): { date: string; hm: string } {
  let f = fmts.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit",
                                           hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    fmts.set(tz, f);
  }
  const p = Object.fromEntries(f.formatToParts(new Date(t)).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, hm: `${p.hour}:${p.minute}` };
}

/** YYYY-MM of every local month the file touches, oldest first. */
export function monthsIn(table: TideTable, tz: string): string[] {
  const out: string[] = [];
  const end = Date.parse(table.to) - 60000;
  for (let t = Date.parse(table.from); ; t += 86400000 * 27) {
    const m = local(tz, Math.min(t, end)).date.slice(0, 7);
    if (out[out.length - 1] !== m) out.push(m);
    if (t >= end) break;
  }
  return out;
}

export function monthTurns(table: TideTable, ym: string, tz: string): MonthTurn[] {
  const from = Date.parse(table.from);
  const out: MonthTurn[] = [];
  for (const [min, cm, hi] of table.turns) {
    const l = local(tz, from + min * 60000);
    if (l.date.startsWith(ym)) out.push({ date: l.date, hm: l.hm, h: cm / 100, hi: hi === 1 });
  }
  return out;
}

export function toCsv(rows: MonthTurn[], unit: Unit): string {
  const head = `date,time,tide,height_${unit}\n`;
  return head + rows.map((r) => `${r.date},${r.hm},${r.hi ? "high" : "low"},${unit === "ft" ? (r.h * FT).toFixed(1) : r.h.toFixed(2)}\n`).join("");
}

/** One local day from the table: its turns and length, and the turns of the days either side, all in
 * minutes from the day's local midnight (for the chart). Used when the visitor's today is not in the
 * embedded month (the page was built before the month turned over in the station's zone). */
export function dayFromTable(table: TideTable, date: string, tz: string):
  { date: string; day_minutes: number; tides: Turn[]; around: Turn[] } {
  const m0 = localMidnight(tz, date), m1 = localMidnight(tz, addDays(date, 1));
  const lo = localMidnight(tz, addDays(date, -1)), hi = localMidnight(tz, addDays(date, 2));
  const from = Date.parse(table.from);
  const around: Turn[] = [];
  for (const [min, cm, k] of table.turns) {
    const t = from + min * 60000;
    if (t >= lo && t < hi) around.push([local(tz, t).hm, Math.round((t - m0) / 60000), cm / 100, k]);
  }
  const n = Math.round((m1 - m0) / 60000);
  return { date, day_minutes: n, tides: around.filter((x) => x[1] >= 0 && x[1] < n), around };
}
