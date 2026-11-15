// The embeddable tide widget: options from the query string, data from tides/{path}.json, drawn in
// the station's own time zone. Every string from the URL or the file goes in with textContent.
import { chartPath } from "../station/chart";
import { addDays, dayLabel, height, localDate } from "../station/format";
import { dayFromTable, type TideTable } from "../station/months";
import { parseParams } from "./params";

const TIDES_BASE: string = import.meta.env.PUBLIC_TIDES_BASE || "/tides";
const SVG = "http://www.w3.org/2000/svg";
const W = 400, H = 110;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function svg(name: string, attrs: Record<string, string | number>): SVGElement {
  const n = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
  return n;
}

function wallMinutes(tz: string, now: Date): number {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(now).map((x) => [x.type, x.value]));
  return Number(p.hour) * 60 + Number(p.minute);
}

export async function mountWidget(root: HTMLElement): Promise<void> {
  const o = parseParams(location.search);
  document.body.classList.toggle("light", o.theme === "light");
  const msg = (text: string) => root.replaceChildren(el("p", "w-msg", text));
  if (!o.station) { msg("Choose a place for this widget on the 3Dweather embed page."); return; }

  let table: TideTable | null = null;
  try {
    const r = await fetch(`${TIDES_BASE}/${o.station}.json`);
    table = r.ok ? ((await r.json()) as TideTable) : null;
  } catch { table = null; }
  if (!table) { msg("No tide table for this place."); return; }

  const tz = table.tz || "UTC";
  const name = table.name || o.station.split("/").pop()!;
  const today = localDate(tz, new Date());
  const days = Array.from({ length: o.days }, (_, k) => dayFromTable(table!, addDays(today, k), tz));

  const head = el("p", "w-name");
  const link = el("a", undefined, name);
  link.href = `/${o.station}`;
  link.target = "_blank";
  link.rel = "noopener";
  head.append(link);

  const blocks = days.map((d, k) => {
    const box = el("section", "w-day");
    box.append(el("h2", undefined, k === 0 ? `Today · ${dayLabel(d.date)}` : dayLabel(d.date)));
    const ol = el("ol");
    for (const [hm, , h, hi] of d.tides) {
      const li = el("li", hi ? "hi" : "lo");
      li.append(el("b", undefined, hi ? "High" : "Low"), " ", el("time", undefined, hm), " ", el("span", undefined, height(h, o.unit)));
      ol.append(li);
    }
    if (!d.tides.length) ol.append(el("li", undefined, "No turns"));
    box.append(ol);
    return box;
  });

  const d0 = days[0];
  const hs = d0.around.map((t) => t[2]);
  const lo = Math.min(...hs, 0), hi = Math.max(...hs, 0), pad = Math.max(0.05, (hi - lo) * 0.12);
  const { path } = chartPath(d0, null, d0.around, { w: W, h: H, lo: lo - pad, hi: hi + pad });
  const chart = svg("svg", { class: "w-chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `Tide height today at ${name}` });
  chart.append(svg("path", { class: "area", d: `${path}L${W},${H}L0,${H}Z` }), svg("path", { class: "curve", d: path }));
  const x = (Math.min(d0.day_minutes, wallMinutes(tz, new Date())) / d0.day_minutes) * W;
  chart.append(svg("line", { class: "now", x1: x, x2: x, y1: 0, y2: H }));

  const zone = el("p", "w-zone", `Local time (${tz})`);
  const credit = el("p", "w-credit");
  const by = el("a", undefined, "Tides by 3Dweather");
  by.href = `/${o.station}`;
  by.target = "_blank";
  by.rel = "noopener";
  credit.append(by, " · not for navigation");

  root.replaceChildren(head, blocks[0], chart, ...blocks.slice(1), zone, credit);
}
