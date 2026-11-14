// The flat regional map: four stacked canvases (base, field, flow, top), the timeline, legend,
// units, tap readout and the "next three days" summary.
import { LAYERS, type Layer } from "../globe/layers";
import { loadLatest } from "../globe/manifest";
import { formatCoord, Probe, readoutFor } from "../globe/probe";
import { initialHour, mountTimeline, type TimelineHandle } from "../globe/timeline";
import { mountLegend } from "../globe/ui";
import { mountUnitsMenu, type Units } from "../globe/units";
import { fieldPixels, sampleRegion, windAt } from "./field";
import { clampFlat, fitScale, initialView, projectFlat, unprojectFlat, xScale, type FlatGeom, type FlatView } from "./flat";
import { loadRegionManifest, loadSheet, type RegionManifest, type Sheet } from "./sheet";
import { peakSummary } from "./summary";

export type RegionLayer = "rain" | "wind";
export type RegionMapHandle = {
  ready: boolean;
  layer(): RegionLayer;
  setLayer(id: RegionLayer): void;
  hour(): number;
  setHour(h: number): void;
  view(): FlatView;
  setView(v: FlatView): void;
  manifest(): RegionManifest | null;
};

type Outline = { land: number[][][]; coast: number[][] };

const WX_BASE: string = import.meta.env.PUBLIC_WX_BASE || "/wx";
const ASSET_BASE: string = import.meta.env.PUBLIC_ASSET_BASE || "/assets/globe";
const SEA = "#081a2e";
const LAND = "#1b2636";
const COAST = "rgba(160, 190, 220, 0.75)";
const RETRY_MS = [2000, 5000, 15000, 30000];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function retry<T>(load: () => Promise<T>, notice: (m: string | null) => void): Promise<T> {
  for (let i = 0; ; i++) {
    try {
      const out = await load();
      if (i > 0) notice(null);
      return out;
    } catch {
      notice("The forecast is taking a while to load. Retrying…");
      await sleep(RETRY_MS[Math.min(i, RETRY_MS.length - 1)]);
    }
  }
}

export async function mountRegionMap(
  root: HTMLElement,
  opts: { slug: string; layer: RegionLayer; timeline: HTMLElement; legend: HTMLElement; unitsButton: HTMLButtonElement;
    layerButtons: HTMLElement; summary: HTMLElement },
): Promise<RegionMapHandle> {
  const names = ["base", "field", "flow", "top"] as const;
  const cv = Object.fromEntries(names.map((n) => {
    const c = document.createElement("canvas");
    c.className = `rm-${n}`;
    c.setAttribute("aria-hidden", "true");
    root.append(c);
    return [n, c];
  })) as Record<(typeof names)[number], HTMLCanvasElement>;
  const cx = Object.fromEntries(names.map((n) => [n, cv[n].getContext("2d")!])) as Record<(typeof names)[number], CanvasRenderingContext2D>;
  const notice = document.createElement("p");
  notice.className = "rm-notice";
  notice.setAttribute("role", "status");
  notice.hidden = true;
  root.append(notice);
  const showNotice = (msg: string | null) => { notice.textContent = msg ?? ""; notice.hidden = msg === null; };
  const probe = new Probe(root);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let layerId: RegionLayer = opts.layer;
  let units: Units = mountUnitsMenu(opts.unitsButton, (u) => { units = u; setLegendUnits?.(u); refreshProbe(); showSummary(); });
  let m: RegionManifest | null = null;
  let a: Sheet | null = null, b: Sheet | null = null;
  let outline: Outline = { land: [], coast: [] };
  let view: FlatView = { lon0: 0, lat0: 0, zoom: 1 };
  let hour = 0;
  let timeline: TimelineHandle | null = null;
  let setLegendUnits: ((u: Units) => void) | null = null;
  let dirtyBase = true, dirtyField = true;
  const handle: RegionMapHandle = {
    ready: false,
    layer: () => layerId,
    setLayer: (id) => setLayer(id),
    hour: () => hour,
    setHour: (h) => { timeline?.setHour(h); setHour(h); },
    view: () => view,
    setView: (v) => setView(v),
    manifest: () => m,
  };
  if (import.meta.env.DEV || new URLSearchParams(location.search).has("debug")) (window as any).__region = handle;

  const geom = (): FlatGeom => ({ m: m!, w: root.clientWidth, h: root.clientHeight });
  const layer = (): Layer => LAYERS[layerId];

  function setView(v: FlatView): void {
    if (!m) return;
    view = clampFlat(v, geom());
    dirtyBase = dirtyField = true;
    resetParticles();
  }
  function setHour(h: number): void {
    hour = h;
    dirtyField = flowStale = true;
    refreshProbe();
  }
  function setLayer(id: RegionLayer): void {
    layerId = id;
    opts.layerButtons.querySelectorAll<HTMLButtonElement>("button[data-layer]").forEach((x) =>
      x.setAttribute("aria-pressed", String(x.dataset.layer === id)));
    setLegendUnits = mountLegend(opts.legend, layer(), units);
    dirtyField = true;
    resetParticles();
    cx.flow.setTransform(1, 0, 0, 1, 0, 0);
    cx.flow.clearRect(0, 0, cv.flow.width, cv.flow.height);
    refreshProbe();
  }
  opts.layerButtons.addEventListener("click", (e) => {
    const btn = (e.target as Element).closest<HTMLButtonElement>("button[data-layer]");
    if (btn) setLayer(btn.dataset.layer as RegionLayer);
  });

  // --- drawing ---
  const dpr = () => Math.min(2, window.devicePixelRatio || 1);
  function sizeCanvases(): boolean {
    const d = dpr(), w = Math.round(root.clientWidth * d), h = Math.round(root.clientHeight * d);
    if (cv.base.width === w && cv.base.height === h) return false;
    for (const n of names) { cv[n].width = w; cv[n].height = h; }
    return true;
  }
  function path(ctx: CanvasRenderingContext2D, flat: number[], close: boolean): void {
    const g = geom();
    for (let i = 0; i < flat.length; i += 2) {
      const p = projectFlat(view, g, flat[i + 1], flat[i]);
      if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y);
    }
    if (close) ctx.closePath();
  }
  function drawBase(): void {
    const ctx = cx.base, g = geom();
    ctx.setTransform(dpr(), 0, 0, dpr(), 0, 0);
    ctx.fillStyle = SEA;
    ctx.fillRect(0, 0, g.w, g.h);
    // graticule every 5 or 10 degrees
    const span = g.w / (fitScale(g) * view.zoom * xScale(m!));
    const step = span > 40 ? 10 : 5;
    ctx.strokeStyle = "rgba(120, 160, 200, 0.12)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let lon = Math.ceil(m!.west / step) * step; lon <= m!.east; lon += step) {
      const p = projectFlat(view, g, 0, lon);
      ctx.moveTo(p.x, 0); ctx.lineTo(p.x, g.h);
    }
    for (let lat = Math.ceil(m!.south / step) * step; lat <= m!.north; lat += step) {
      const p = projectFlat(view, g, lat, 0);
      ctx.moveTo(0, p.y); ctx.lineTo(g.w, p.y);
    }
    ctx.stroke();
    ctx.fillStyle = LAND;
    ctx.beginPath();
    for (const poly of outline.land) for (const ring of poly) path(ctx, ring, true);
    ctx.fill("evenodd");
  }
  const scratch = document.createElement("canvas");
  function drawField(): void {
    const ctx = cx.field, g = geom();
    ctx.setTransform(dpr(), 0, 0, dpr(), 0, 0);
    ctx.clearRect(0, 0, g.w, g.h);
    if (!a || !b || !m) return;
    scratch.width = m.w; scratch.height = m.h;
    const sctx = scratch.getContext("2d")!;
    sctx.putImageData(new ImageData(fieldPixels(a, b, m, hour, layer()), m.w, m.h), 0, 0);
    // cell centres sit on the grid nodes: the image spans half a cell beyond them
    const dlon = (m.east - m.west) / (m.w - 1), dlat = (m.north - m.south) / (m.h - 1);
    const tl = projectFlat(view, g, m.north + dlat / 2, m.west - dlon / 2);
    const br = projectFlat(view, g, m.south - dlat / 2, m.east + dlon / 2);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(scratch, tl.x, tl.y, br.x - tl.x, br.y - tl.y);
  }
  function drawTop(): void {
    const ctx = cx.top, g = geom();
    ctx.setTransform(dpr(), 0, 0, dpr(), 0, 0);
    ctx.clearRect(0, 0, g.w, g.h);
    ctx.strokeStyle = COAST;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (const line of outline.coast) path(ctx, line, false);
    ctx.stroke();
    ctx.font = "12px system-ui, sans-serif";
    ctx.textBaseline = "middle";
    for (const [name, lat, lon] of m!.cities) {
      const p = projectFlat(view, g, lat, lon);
      if (p.x < -40 || p.y < -10 || p.x > g.w + 40 || p.y > g.h + 10) continue;
      ctx.fillStyle = "#e8f0f8";
      ctx.beginPath();
      ctx.arc(p.x, p.y, 2.5, 0, 2 * Math.PI);
      ctx.fill();
      ctx.lineWidth = 3;
      ctx.strokeStyle = "rgba(4, 12, 24, 0.85)";
      ctx.strokeText(name, p.x + 6, p.y);
      ctx.fillText(name, p.x + 6, p.y);
    }
    const at = probe.at();
    if (at) {
      const p = projectFlat(view, g, at.lat, at.lon);
      ctx.beginPath();
      ctx.arc(p.x, p.y, 6, 0, 2 * Math.PI);
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#3fe0ff";
      ctx.stroke();
    }
  }

  // --- wind particles (flat) ---
  type P = { lat: number; lon: number; age: number };
  let parts: P[] = [];
  function spawn(p?: P): P {
    const g = geom();
    const ll = unprojectFlat(view, g, Math.random() * g.w, Math.random() * g.h);
    const out = p ?? { lat: 0, lon: 0, age: 0 };
    out.lat = ll.lat; out.lon = ll.lon; out.age = Math.floor(Math.random() * 120);
    return out;
  }
  let flowStale = true; // reduced motion: still streaks, redrawn only when something changes
  function resetParticles(): void { parts = []; flowStale = true; }
  function drawFlow(): void {
    if (layerId !== "wind" || !a || !m) return;
    if (reduced && !flowStale) return;
    const g = geom(), ctx = cx.flow;
    const want = Math.max(200, Math.min(2500, Math.round((g.w * g.h) / 700)));
    while (parts.length < want) parts.push(spawn());
    if (parts.length > want) parts.length = want;
    ctx.setTransform(dpr(), 0, 0, dpr(), 0, 0);
    if (reduced) ctx.clearRect(0, 0, g.w, g.h);
    else {
      ctx.globalCompositeOperation = "destination-in";
      ctx.fillStyle = "rgba(0, 0, 0, 0.92)";
      ctx.fillRect(0, 0, g.w, g.h);
      ctx.globalCompositeOperation = "source-over";
    }
    ctx.strokeStyle = "rgba(255, 255, 255, 0.75)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let step = reduced ? 12 : 1; step > 0; step--) advance(g, ctx);
    ctx.stroke();
    flowStale = false;
  }
  function advance(g: FlatGeom, ctx: CanvasRenderingContext2D): void {
    const s = fitScale(g) * view.zoom, k = xScale(m!);
    for (const p of parts) {
      const w = windAt(a!, m!, hour, p.lat, p.lon);
      if (!w || ++p.age > 160) { spawn(p); continue; }
      const from = projectFlat(view, g, p.lat, p.lon);
      p.lon += (w.u * 0.22) / (k * s);
      p.lat += (w.v * 0.22) / s;
      const to = projectFlat(view, g, p.lat, p.lon);
      if (to.x < 0 || to.y < 0 || to.x > g.w || to.y > g.h) { spawn(p); continue; }
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
    }
  }

  function frame(): void {
    if (m) {
      if (sizeCanvases()) { dirtyBase = dirtyField = true; view = clampFlat(view, geom()); resetParticles(); }
      if (dirtyBase) { drawBase(); drawTop(); dirtyBase = false; }
      if (dirtyField) { drawField(); drawTop(); dirtyField = false; }
      if (!document.hidden) drawFlow();
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  new ResizeObserver(() => { dirtyBase = dirtyField = true; }).observe(root);

  // --- probe ---
  function refreshProbe(): void {
    const at = probe.at();
    if (!at || !m) return;
    const s = a && b ? sampleRegion(a, b, m, hour, at.lat, at.lon) : null;
    probe.show(at.lat, at.lon, s ? readoutFor(layer(), s, at.lat, at.lon, units) : ["No forecast data here", formatCoord(at.lat, at.lon)]);
    drawTop();
  }
  function probeAt(lat: number, lon: number): void {
    probe.show(lat, lon, []);
    refreshProbe();
  }
  probe.onHide = () => drawTop();

  // --- gestures: mouse drag pans, ctrl+wheel (or wheel once the map is active) zooms;
  // touch: one finger scrolls the page and taps, two fingers pan and pinch ---
  const pointers = new Map<number, { x: number; y: number }>();
  let downAt: { x: number; y: number; t: number } | null = null;
  let active = false;
  let pinch: { d: number; zoom: number; mid: { x: number; y: number } } | null = null;
  const local = (e: PointerEvent | WheelEvent | MouseEvent) => {
    const r = root.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  function zoomAround(pt: { x: number; y: number }, factor: number): void {
    if (!m) return;
    const g = geom();
    const before = unprojectFlat(view, g, pt.x, pt.y);
    const next = { ...view, zoom: Math.max(1, Math.min(8, view.zoom * factor)) };
    const after = unprojectFlat(next, g, pt.x, pt.y);
    setView({ zoom: next.zoom, lon0: next.lon0 + before.lon - after.lon, lat0: next.lat0 + before.lat - after.lat });
  }
  root.addEventListener("pointerdown", (e) => {
    if ((e.target as Element).closest(".probe")) return;
    active = true;
    pointers.set(e.pointerId, local(e));
    downAt = { ...local(e), t: performance.now() };
    if (pointers.size === 2) {
      const [p, q] = [...pointers.values()];
      pinch = { d: Math.hypot(p.x - q.x, p.y - q.y), zoom: view.zoom, mid: { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 } };
      downAt = null;
    }
    if (e.pointerType === "mouse") root.setPointerCapture(e.pointerId);
  });
  root.addEventListener("pointermove", (e) => {
    const prev = pointers.get(e.pointerId);
    if (!prev || !m) return;
    const cur = local(e);
    pointers.set(e.pointerId, cur);
    const g = geom(), s = fitScale(g) * view.zoom;
    if (pinch && pointers.size === 2) {
      const [p, q] = [...pointers.values()];
      const mid = { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 };
      zoomAround(mid, (pinch.zoom * Math.hypot(p.x - q.x, p.y - q.y)) / pinch.d / view.zoom);
      const s2 = fitScale(g) * view.zoom;
      setView({ ...view, lon0: view.lon0 - (mid.x - pinch.mid.x) / (xScale(m) * s2), lat0: view.lat0 + (mid.y - pinch.mid.y) / s2 });
      pinch.mid = mid;
    } else if (e.pointerType === "mouse" && e.buttons === 1) {
      setView({ ...view, lon0: view.lon0 - (cur.x - prev.x) / (xScale(m) * s), lat0: view.lat0 + (cur.y - prev.y) / s });
    }
  });
  const up = (e: PointerEvent) => {
    const p = pointers.get(e.pointerId);
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinch = null;
    if (p && downAt && m && Math.hypot(p.x - downAt.x, p.y - downAt.y) < 6 && performance.now() - downAt.t < 600) {
      const ll = unprojectFlat(view, geom(), p.x, p.y);
      probeAt(ll.lat, ll.lon);
    }
    downAt = null;
  };
  root.addEventListener("pointerup", up);
  root.addEventListener("pointercancel", (e) => { pointers.delete(e.pointerId); pinch = null; downAt = null; });
  root.addEventListener("pointerleave", () => { active = false; });
  root.addEventListener("wheel", (e) => {
    if (!(e.ctrlKey || e.metaKey || active)) return; // plain scrolling keeps scrolling the page
    e.preventDefault();
    zoomAround(local(e), Math.exp(-e.deltaY * 0.0015));
  }, { passive: false });
  root.addEventListener("dblclick", (e) => zoomAround(local(e), 2));
  root.tabIndex = 0;
  root.addEventListener("keydown", (e) => {
    if (!m) return;
    const g = geom(), s = fitScale(g) * view.zoom, stepPx = 60;
    const moves: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1] };
    if (e.key === "+" || e.key === "=") zoomAround({ x: g.w / 2, y: g.h / 2 }, 1.5);
    else if (e.key === "-") zoomAround({ x: g.w / 2, y: g.h / 2 }, 1 / 1.5);
    else if (moves[e.key]) setView({ ...view, lon0: view.lon0 + (moves[e.key][0] * stepPx) / (xScale(m) * s), lat0: view.lat0 + (moves[e.key][1] * stepPx) / s });
    else return;
    e.preventDefault();
  });

  // --- summary ---
  function showSummary(): void {
    if (!m) return;
    const s = peakSummary(m, units);
    const row = (key: "wind" | "rain", title: string) => {
      const p = s[key];
      return `<li><button type="button" class="rm-peak" data-peak="${key}"><span class="rm-peak-title">${title}</span>
        <strong>${p.value}</strong> <span>on ${p.when} ${m!.place} time, ${p.where}.</span></button></li>`;
    };
    opts.summary.innerHTML = `<ul class="rm-peaks">${row("wind", "Strongest wind")}${row("rain", "Heaviest rain")}</ul>`;
  }
  opts.summary.addEventListener("click", (e) => {
    const btn = (e.target as Element).closest<HTMLButtonElement>("button[data-peak]");
    if (!btn || !m) return;
    const key = btn.dataset.peak as "wind" | "rain";
    const p = peakSummary(m, units)[key];
    setLayer(key);
    handle.setHour(p.hour);
    setView({ lon0: p.lon, lat0: p.lat, zoom: Math.max(view.zoom, 3) });
    probeAt(p.lat, p.lon);
    root.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" });
  });

  // --- loading ---
  setLegendUnits = mountLegend(opts.legend, layer(), units);
  void retry(async () => {
    const r = await fetch(`${ASSET_BASE}/regions/${opts.slug}.json`);
    if (!r.ok) throw new Error(`regions/${opts.slug}.json: HTTP ${r.status}`);
    return (await r.json()) as Outline;
  }, showNotice).then((o) => { outline = o; dirtyBase = true; });

  const latest = await retry(() => loadLatest(WX_BASE), showNotice);
  m = await retry(() => loadRegionManifest(WX_BASE, latest.dir, opts.slug), showNotice);
  view = clampFlat(initialView(m), geom());
  dirtyBase = dirtyField = true;
  showSummary();
  [a, b] = await retry(() => Promise.all([
    loadSheet(`${WX_BASE}/${latest.dir}/${opts.slug}-a.webp`),
    loadSheet(`${WX_BASE}/${latest.dir}/${opts.slug}-b.webp`),
  ]), showNotice);
  const hours = m.hours - 1;
  hour = initialHour(m.run, new Date(), hours);
  timeline = mountTimeline(opts.timeline, { hours, runIso: m.run, timeZone: m.tz, onHour: (h) => setHour(h) });
  timeline.setHour(hour);
  new IntersectionObserver(([e]) => timeline!.setSuspended(!e.isIntersecting)).observe(root);
  timeline.setPlaying(!reduced);
  setLayer(layerId);
  dirtyField = true;
  handle.ready = true;
  return handle;
}
