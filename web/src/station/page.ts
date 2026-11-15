// Station page browser script: the tide chart with a "now" line, the day picker (month table rows),
// the m/ft switch, the weather strip from the latest forecast run, and other months + CSV.
import { chartPath } from "./chart";
import { dayLabel, height, todayIndex, type StationData, type Turn, type Unit } from "./format";
import { monthTurns, monthsIn, toCsv, type MonthTurn, type TideTable } from "./months";
import { loadWeather, type WxSeries } from "./weather";

type PageData = StationData & { path: string; cc: string; region: string };

const WX_BASE: string = import.meta.env.PUBLIC_WX_BASE || "/wx";
const TIDES_BASE: string = import.meta.env.PUBLIC_TIDES_BASE || "/tides";
const UNIT_KEY = "st-unit";
const W = 600, H = 200, TOP = 14, BOTTOM = 22;
const SVG = "http://www.w3.org/2000/svg";

const el = document.getElementById("st-data");
if (el) start(JSON.parse(el.textContent || "null") as PageData);

function readUnit(): Unit {
  try { return localStorage.getItem(UNIT_KEY) === "ft" ? "ft" : "m"; } catch { return "m"; }
}
function saveUnit(u: Unit): void {
  try { localStorage.setItem(UNIT_KEY, u); } catch { /* private mode: not remembered */ }
}

/** Wall-clock minutes since local midnight in `tz`. */
function localMinutes(tz: string, now: Date): number {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(now).map((x) => [x.type, x.value]));
  return Number(p.hour) * 60 + Number(p.minute);
}

function start(data: PageData): void {
  const days = data.days;
  let today = todayIndex(days, data.tz, new Date());
  if (today < 0) today = Math.max(0, days.findIndex((d) => d.date === data.today));
  let pick = today;
  let unit = readUnit();

  const all = days.flatMap((d) => d.tides.map((t) => t[2]));
  const lo0 = all.length ? Math.min(...all) : -1, hi0 = all.length ? Math.max(...all) : 1;
  const pad = Math.max(0.05, (hi0 - lo0) * 0.12);
  const range = { lo: lo0 - pad, hi: hi0 + pad };

  const svg = document.querySelector<SVGSVGElement>("svg[data-chart]");
  const turnsList = document.querySelector<HTMLElement>("[data-turns]");
  const dayLabelEl = document.querySelector<HTMLElement>("[data-day-label]");

  function neighbourTurns(i: number): Turn[] {
    const out: Turn[] = [];
    if (i > 0) out.push(...days[i - 1].tides.map((t) => [t[0], t[1] - days[i - 1].day_minutes, t[2], t[3]] as Turn));
    out.push(...days[i].tides);
    if (i + 1 < days.length) out.push(...days[i + 1].tides.map((t) => [t[0], t[1] + days[i].day_minutes, t[2], t[3]] as Turn));
    return out;
  }

  function node(name: string, attrs: Record<string, string | number>, text?: string): SVGElement {
    const n = document.createElementNS(SVG, name);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
    if (text != null) n.textContent = text;
    return n;
  }

  function drawChart(): void {
    if (!svg || !data.has_tides) return;
    const d = days[pick];
    const n = d.day_minutes;
    const size = { w: W, h: H - TOP - BOTTOM, ...range };
    const { path, marks } = chartPath(d, data.curve, neighbourTurns(pick), size);
    svg.replaceChildren();
    const g = node("g", { transform: `translate(0 ${TOP})` });
    const x = (m: number) => (m / n) * W;
    if (d.sunrise) g.append(node("rect", { class: "night", x: 0, y: -TOP, width: x(d.sunrise[1]), height: H }));
    if (d.sunset) g.append(node("rect", { class: "night", x: x(d.sunset[1]), y: -TOP, width: W - x(d.sunset[1]), height: H }));
    const zero = size.h - ((0 - range.lo) / (range.hi - range.lo)) * size.h;
    g.append(node("line", { class: "axis", x1: 0, x2: W, y1: zero, y2: zero }));
    g.append(node("path", { class: "area", d: `${path}L${W},${size.h}L0,${size.h}Z` }));
    g.append(node("path", { class: "curve", d: path, "data-curve": "" }));
    for (let h = 6; h < 24; h += 6) g.append(node("text", { x: x(h * 60), y: size.h + 16, "text-anchor": "middle" }, `${String(h).padStart(2, "0")}:00`));
    for (const m of marks) {
      g.append(node("circle", { cx: m.x, cy: m.y, r: 3.5, class: m.hi ? "hi" : "lo", fill: m.hi ? "#7fd8ff" : "#9fb3c8" }));
      const ty = m.hi ? m.y - 7 : m.y + 14;
      const anchor = m.x < 30 ? "start" : m.x > W - 30 ? "end" : "middle";
      g.append(node("text", { x: m.x, y: ty, "text-anchor": anchor }, `${m.hm} ${height(m.h, unit)}`));
    }
    if (pick === today) {
      const now = x(Math.min(n, localMinutes(data.tz, new Date())));
      g.append(node("line", { class: "now", x1: now, x2: now, y1: -TOP, y2: size.h, "data-now": "" }));
    }
    svg.append(g);
  }

  function drawTurns(): void {
    if (!turnsList) return;
    turnsList.replaceChildren(...days[pick].tides.map(([hm, , h, hi]) => {
      const li = document.createElement("li");
      li.className = hi ? "hi" : "lo";
      li.innerHTML = `<b>${hi ? "High" : "Low"}</b> <time>${hm}</time> <span data-h="${h}">${height(h, unit)}</span>`;
      return li;
    }));
    if (dayLabelEl) dayLabelEl.textContent = dayLabel(days[pick].date);
  }

  function applyUnit(): void {
    document.querySelectorAll<HTMLElement>("[data-h]").forEach((s) => { s.textContent = height(Number(s.dataset.h), unit); });
    document.querySelectorAll<HTMLButtonElement>("[data-unit]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.unit === unit)));
    drawChart();
  }

  document.querySelectorAll<HTMLButtonElement>("[data-unit]").forEach((b) => b.addEventListener("click", () => {
    unit = b.dataset.unit === "ft" ? "ft" : "m";
    saveUnit(unit);
    applyUnit();
  }));

  const rows = document.querySelectorAll<HTMLTableRowElement>(".st-month tbody tr");
  rows.forEach((r) => r.classList.toggle("today", Number(r.dataset.i) === today));
  document.querySelectorAll<HTMLButtonElement>("[data-pick]").forEach((b) => b.addEventListener("click", () => {
    pick = Number(b.dataset.pick);
    rows.forEach((r) => r.classList.toggle("picked", Number(r.dataset.i) === pick));
    drawTurns();
    drawChart();
    document.querySelector(".st-today")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }));

  if (pick !== Math.max(0, days.findIndex((d) => d.date === data.today))) drawTurns();
  applyUnit();
  if (data.has_tides) setupMonths(data, () => unit);
  loadWeather(WX_BASE, data.cc, data.region, data.id).then((w) => { if (w) drawWeather(w, data.tz); });
}

// --- weather -------------------------------------------------------------------------------------

const ARROWS = ["↓", "↙", "←", "↖", "↑", "↗", "→", "↘"]; // direction the wind blows toward, from "from" degrees

function drawWeather(w: WxSeries, tz: string): void {
  const section = document.querySelector<HTMLElement>("[data-weather]");
  const body = document.querySelector<HTMLElement>("[data-weather-body]");
  if (!section || !body) return;
  const now = Date.now() - 3 * 3600000;
  const idx = w.times.map((t, k) => [t, k] as const).filter(([t]) => t.getTime() >= now).map(([, k]) => k);
  if (!idx.length) return;
  const head = new Intl.DateTimeFormat("en-GB", { timeZone: tz, weekday: "short", hour: "2-digit", hourCycle: "h23" });
  const num = (v: number | null | undefined, digits = 0) => (v == null ? "–" : v.toFixed(digits));
  const kmh = (v: number | null | undefined) => (v == null ? "–" : String(Math.round(v * 3.6)));
  const arrow = (deg: number | null | undefined) => (deg == null ? "" : ARROWS[Math.round(deg / 45) % 8]);
  const lines: [string, (k: number) => string, string[]][] = [
    ["Air °C", (k) => num(w.rows[k].t), ["t"]],
    ["Wind km/h", (k) => `${arrow(w.rows[k].wd)} ${kmh(w.rows[k].ws)}`, ["ws"]],
    ["Gust km/h", (k) => kmh(w.rows[k].g), ["g"]],
    ["Rain mm/h", (k) => num(w.rows[k].r, 1), ["r"]],
    ["Cloud %", (k) => num(w.rows[k].c), ["c"]],
    ["Waves m", (k) => num(w.rows[k].wh, 1), ["wh"]],
    ["Period s", (k) => num(w.rows[k].wp), ["wp"]],
    ["Sea °C", (k) => num(w.rows[k].sst), ["sst"]],
  ];
  const used = lines.filter(([, , f]) => idx.some((k) => w.rows[k][f[0]] != null));
  const th = idx.map((k) => `<th scope="col">${head.format(w.times[k])}</th>`).join("");
  const tr = used.map(([label, cell]) => `<tr><th scope="row">${label}</th>${idx.map((k) => `<td>${cell(k)}</td>`).join("")}</tr>`).join("");
  body.innerHTML = `<div class="st-scroll"><table class="st-wx"><thead><tr><th></th>${th}</tr></thead><tbody>${tr}</tbody></table></div>`
    + `<p class="st-note">Forecast run ${w.run}: NOAA GFS and GFS-Wave, ECMWF IFS (CC BY 4.0) via Open-Meteo.</p>`;
  section.hidden = false;
}

// --- other months and CSV ------------------------------------------------------------------------

function setupMonths(data: PageData, unit: () => Unit): void {
  const select = document.querySelector<HTMLSelectElement>("select[data-month]");
  const csv = document.querySelector<HTMLButtonElement>("button[data-csv]");
  if (!select || !csv) return;
  const current = data.days[0].date.slice(0, 7);
  const out = document.createElement("div");
  out.className = "st-other";
  select.closest("p")?.after(out);
  let table: Promise<TideTable | null> | null = null;
  const load = () => (table ??= fetch(`${TIDES_BASE}/${data.path}.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null));
  const monthName = (ym: string) => new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" })
    .format(new Date(`${ym}-15T00:00:00Z`));

  load().then((t) => {
    if (!t) { select.disabled = true; return; }
    for (const ym of monthsIn(t, data.tz)) {
      const o = document.createElement("option");
      o.value = ym;
      o.textContent = ym === current ? `${monthName(ym)} (this month)` : monthName(ym);
      select.append(o);
    }
  });

  select.addEventListener("change", async () => {
    const t = await load();
    out.replaceChildren();
    if (!t || !select.value || select.value === current) return;
    out.append(monthTable(monthTurns(t, select.value, data.tz), unit(), monthName(select.value)));
  });

  csv.addEventListener("click", async () => {
    const t = await load();
    const ym = select.value || current;
    const rows: MonthTurn[] = t ? monthTurns(t, ym, data.tz)
      : data.days.flatMap((d) => d.tides.map(([hm, , h, hi]) => ({ date: d.date, hm, h, hi: hi === 1 })));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([toCsv(rows, unit())], { type: "text/csv" }));
    a.download = `tides-${data.path.split("/").pop()}-${ym}.csv`;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });
}

function monthTable(rows: MonthTurn[], unit: Unit, title: string): HTMLElement {
  const byDay = new Map<string, MonthTurn[]>();
  for (const r of rows) byDay.set(r.date, [...(byDay.get(r.date) ?? []), r]);
  const wrap = document.createElement("div");
  wrap.className = "st-scroll";
  const body = [...byDay].map(([date, ts]) => `<tr><th scope="row">${dayLabel(date)}</th><td class="st-cell-tides">${
    ts.map((r) => `<span class="${r.hi ? "hi" : "lo"}">${r.hi ? "▲" : "▼"} ${r.hm} <span data-h="${r.h}">${height(r.h, unit)}</span></span>`).join("")
  }</td></tr>`).join("");
  wrap.innerHTML = `<table class="st-month st-month-other"><caption>${title}</caption><thead><tr><th scope="col">Day</th><th scope="col">Tides</th></tr></thead><tbody>${body}</tbody></table>`;
  return wrap;
}
