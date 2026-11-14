// Mounts the globe: canvases, data loading, view state and the draw loop.
import { flowVector, landGridFrom, sampleLayer, type Frames, type LandGrid } from "./field";
import { flowSteps, particleCount, Particles, spawnOnDisk } from "./particles";
import { LayerFrames, RETRY_DELAYS_MS, LOAD_NOTICE } from "./frames";
import { attachGestures } from "./gestures";
import { formatHash, parseHash } from "./hash";
import { drawOverlay } from "./overlay";
import { initialHour, mountTimeline, type TimelineHandle } from "./timeline";
import { biggestWave, FLY_MS, FLY_ZOOM, flyView, peakAt } from "./fly";
import { LAYERS, type Layer, type LayerId } from "./layers";
import { formatCoord, Probe, readoutFor } from "./probe";
import type { Intro } from "../splash/intro";
import { mountLegend } from "./ui";
import { loadUnits, mountUnitsMenu, type Units } from "./units";
import { loadLatest, loadManifest, type GlobeManifest, type Latest } from "./manifest";
import { GlobeRenderer } from "./renderer";
import { highestTide, loadTideAtlas, phasesAt, tideAt, type TideAtlas } from "./tide";
import { clampView, project, radiusPx, unproject, type View } from "./view";

export type GlobeHandle = {
  ready: boolean;
  drawn: boolean;
  view(): View;
  setView(v: View): void;
  hour(): number;
  setHour(h: number): Promise<void>;
  /** Splash inputs; null = normal drawing. */
  setIntro(i: Intro | null): void;
  /** The layer on show, and switching to another (frames reload; the view and hour stay). */
  layer(): LayerId;
  setLayer(id: LayerId): Promise<void>;
  /** Run time, grid cell count and the layer's model once the manifest has loaded. */
  info(): { run: string; cells: number; model: string } | null;
  /** Resolves when the first forecast frame is on the globe. */
  loaded: Promise<void>;
};

export const DEFAULT_VIEW: View = { lat0: 20, lon0: 0, zoom: 1 };

const WX_BASE: string = import.meta.env.PUBLIC_WX_BASE || "/wx";
const ASSET_BASE: string = import.meta.env.PUBLIC_ASSET_BASE || "/assets/globe";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function loadBitmap(url: string): Promise<ImageBitmap> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return createImageBitmap(await res.blob(), { colorSpaceConversion: "none", premultiplyAlpha: "none" });
}

/** Retry a load with the same backoff as the sprites, showing the notice meanwhile. */
async function withRetry<T>(load: () => Promise<T>, notice: (m: string | null) => void): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      const out = await load();
      if (attempt > 0) notice(null);
      return out;
    } catch {
      notice(LOAD_NOTICE);
      await sleep(RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)]);
    }
  }
}

export async function initGlobe(
  root: HTMLElement,
  opts: { layer?: LayerId; timeline?: HTMLElement; legend?: HTMLElement; unitsButton?: HTMLButtonElement; biggestButton?: HTMLButtonElement } = {},
): Promise<GlobeHandle | null> {
  const canvas = document.createElement("canvas");
  canvas.className = "globe-gl";
  canvas.setAttribute("aria-hidden", "true");
  const notice = document.createElement("p");
  notice.className = "globe-notice";
  notice.setAttribute("role", "status");
  notice.hidden = true;
  root.append(canvas, notice);
  let failLoad = () => {};
  const showNotice = (m: string | null) => {
    notice.textContent = m ?? "";
    notice.hidden = m === null;
    if (m !== null) failLoad();
  };

  const overlay = document.createElement("canvas");
  overlay.className = "globe-overlay";
  overlay.setAttribute("aria-hidden", "true");
  canvas.after(overlay);
  const ctx = overlay.getContext("2d")!;
  let coast: number[][] = [];

  const flow = document.createElement("canvas");
  flow.className = "globe-flow";
  flow.setAttribute("aria-hidden", "true");
  overlay.after(flow);
  const fctx = flow.getContext("2d")!;
  const particles = new Particles();
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const coarse = window.matchMedia("(pointer: coarse)").matches;
  let onScreen = true;
  let flowStale = true; // reduced motion: redraw the still trails

  let renderer: GlobeRenderer;
  try {
    renderer = new GlobeRenderer(canvas);
  } catch (err) {
    // No WebGL, or the shader failed on this GPU: say so rather than leave an empty box.
    console.warn(err);
    root.replaceChildren();
    const msg = document.createElement("p");
    msg.className = "globe-fallback";
    msg.textContent = "This map needs WebGL, which this browser or device isn't providing.";
    root.append(msg);
    return null;
  }
  let view = parseHash(location.hash) ?? DEFAULT_VIEW;
  let hour = 0;
  let dirty = true;
  let overlayDirty = true;
  let landReady = false;
  let dataReady = false;
  let manifest: GlobeManifest | null = null;
  let latest: Latest | null = null;
  let layer: Layer = LAYERS[opts.layer ?? "waves"];
  renderer.setLayer(layer);
  let store: LayerFrames | null = null;
  let shown = { a: -1, b: -1 };
  // CPU copies for particles, the probe and the peak search.
  let frames: Frames | null = null;
  let land: LandGrid | null = null;
  // Tide atlas: loaded the first time the tide layer is shown, then kept.
  let tide: TideAtlas | null = null;
  let tideLoad: Promise<TideAtlas> | null = null;
  const isTide = () => layer.shade.kind === "tide";
  const timeAt = (h: number) => new Date(Date.parse(latest!.run) + h * 3.6e6);
  function ensureTide(): Promise<TideAtlas> {
    tideLoad ??= withRetry(() => loadTideAtlas(ASSET_BASE), showNotice).then((a) => {
      tide = a;
      renderer.setTideAtlas(a);
      return a;
    });
    return tideLoad;
  }
  const unitListeners: ((u: Units) => void)[] = [];
  let units: Units = opts.unitsButton
    ? mountUnitsMenu(opts.unitsButton, (u) => { units = u; unitListeners.forEach((f) => f(u)); })
    : loadUnits();

  const handle: GlobeHandle = {
    ready: false,
    drawn: false,
    view: () => view,
    setView: (v) => setView(v),
    hour: () => hour,
    setHour: (h) => { timeline?.setHour(h); return setHour(h); },
    setIntro: (i) => {
      intro = i;
      dirty = overlayDirty = flowStale = true;
    },
    layer: () => layer.id,
    setLayer: (id) => switchLayer(id),
    info: () => (info ? { ...info, model: layer.model } : null),
    loaded: Promise.resolve(),
  };
  let intro: Intro | null = null;
  let info: { run: string; cells: number } | null = null;
  const drawnView = (): View => (intro ? { ...view, zoom: view.zoom * intro.zoom } : view);
  let timeline: TimelineHandle | null = null;
  function setHour(h: number): Promise<void> {
    hour = h;
    return applyHour();
  }
  if (import.meta.env.DEV || new URLSearchParams(location.search).has("debug")) (window as any).__globe = handle;

  // The hash follows the view, written once the view has settled.
  let hashTimer = 0;
  function setView(v: View): void {
    view = clampView(v);
    dirty = overlayDirty = flowStale = true;
    clearTimeout(hashTimer);
    hashTimer = window.setTimeout(() => history.replaceState(null, "", formatHash(view)), 600);
  }
  window.addEventListener("hashchange", () => {
    const v = parseHash(location.hash);
    if (v) { view = v; dirty = overlayDirty = flowStale = true; }
  });

  new ResizeObserver(() => { dirty = overlayDirty = flowStale = true; }).observe(root);
  new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; }).observe(root);
  const probe = new Probe(root);
  probe.onHide = () => { flowStale = true; };
  function refreshProbe(): void {
    const at = probe.at();
    if (!at) return;
    const { lat, lon } = at;
    let lines: string[];
    if (isTide()) {
      // The atlas's own 0.5° sea mask decides (the CPU land grid is too coarse for bays);
      // the land grid only picks the wording where the atlas has no sea.
      const t = tide && latest ? tideAt(tide, lat, lon, timeAt(hour)) : undefined;
      if (t === undefined) lines = ["Tide still loading…", formatCoord(lat, lon)];
      else if (t) lines = readoutFor(layer, { tideM: t.heightM, tideRising: t.rising }, lat, lon, units);
      else lines = readoutFor(layer, land?.isLand(lat, lon) ? null : {}, lat, lon, units);
    } else if (!layer.overLand && land?.isLand(lat, lon)) lines = readoutFor(layer, null, lat, lon, units);
    else if (!frames || !manifest) lines = ["Forecast still loading…", formatCoord(lat, lon)];
    else lines = readoutFor(layer, sampleLayer(layer, frames, manifest, lat, lon, hour), lat, lon, units);
    probe.show(lat, lon, lines);
  }
  function probeAt(lat: number, lon: number): void {
    probe.show(lat, lon, []);
    refreshProbe();
    flowStale = true;
  }
  unitListeners.push(() => refreshProbe());

  // Camera flights (Biggest waves). Any press on the globe cancels one.
  let flight = 0;
  function flyTo(to: View, done?: () => void): void {
    cancelAnimationFrame(flight);
    const from = view, t0 = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - t0) / FLY_MS);
      setView(flyView(from, to, t));
      if (t < 1) flight = requestAnimationFrame(tick);
      else { flight = 0; done?.(); }
    };
    flight = requestAnimationFrame(tick);
  }
  root.addEventListener("pointerdown", () => { cancelAnimationFrame(flight); flight = 0; });
  opts.biggestButton?.addEventListener("click", () => {
    if (isTide()) {
      const top = tide && latest ? highestTide(tide, timeAt(hour)) : null;
      if (top) flyTo({ lat0: top.lat, lon0: top.lon, zoom: FLY_ZOOM }, () => probeAt(top.lat, top.lon));
      return;
    }
    if (!frames || !manifest || !land) return;
    // Waves: scan the frame on show; other layers: the pipeline's hourly peak series.
    const w = frames.w;
    const peak = layer.id === "waves" && w ? biggestWave(w.mix < 0.5 ? w.a : w.b, manifest, land) : peakAt(manifest, layer.peak, hour);
    if (!peak) return;
    flyTo({ lat0: peak.lat, lon0: peak.lon, zoom: FLY_ZOOM }, () => probeAt(peak.lat, peak.lon));
  });

  attachGestures(
    root,
    () => view,
    setView,
    () => ({ w: root.clientWidth, h: root.clientHeight }),
    (x, y) => {
      const p = unproject(view, root.clientWidth, root.clientHeight, x, y);
      if (p) probeAt(p.lat, p.lon); else probe.hide();
    },
    () => probe.hide(),
  );

  const frame = () => {
    if (dirty) {
      dirty = false;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = root.clientWidth, h = root.clientHeight;
      const dv = drawnView();
      renderer.body = intro ? intro.body : 1;
      renderer.draw(dv, w, h, dpr);
      // Both canvases share one size and DPR so they stay aligned.
      const ow = Math.round(w * dpr), oh = Math.round(h * dpr);
      if (overlay.width !== ow || overlay.height !== oh) { overlay.width = ow; overlay.height = oh; overlayDirty = true; }
      if (overlayDirty) {
        overlayDirty = false;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        drawOverlay(ctx, dv, w, h, coast, intro ?? undefined);
      }
      if (landReady) handle.drawn = true;
      if (landReady && dataReady) handle.ready = true;
    }
    drawFlow();
    requestAnimationFrame(frame);
  };

  function flowField(lat: number, lon: number) {
    if (!frames || !manifest || !land || !layer.flow) return null;
    if (layer.flow.seaOnly && land.isLand(lat, lon)) return null;
    return flowVector(layer, frames, manifest, lat, lon);
  }

  function drawFlow(): void {
    const w = root.clientWidth, h = root.clientHeight;
    const dpr = Math.min(coarse ? 1.25 : 2, window.devicePixelRatio || 1);
    const fw = Math.round(w * dpr), fh = Math.round(h * dpr);
    if (flow.width !== fw || flow.height !== fh) { flow.width = fw; flow.height = fh; flowStale = true; }
    if (!layer.flow) {
      // Nothing moves on this layer: the canvas only carries the probe marker.
      if (!flowStale) return;
      flowStale = false;
      fctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      fctx.clearRect(0, 0, w, h);
      if (!intro) drawMarker(drawnView(), w, h);
      return;
    }
    const seaOnly = layer.flow.seaOnly;
    if (!frames || !land || !onScreen || document.hidden) return;
    if (reducedMotion && !flowStale) return;
    const dv = drawnView();
    const r = radiusPx(dv.zoom, w, h);
    const want = particleCount(Math.min(Math.PI * r * r, w * h), w);
    const spawn = () => spawnOnDisk(dv, w, h, seaOnly ? land : null, Math.random);
    const gone = (lat: number, lon: number) => {
      if (Math.abs(lat) > 88) return true;
      const p = project(dv, w, h, lat, lon);
      return !p.visible || p.x < -20 || p.y < -20 || p.x > w + 20 || p.y > h + 20;
    };
    const fresh = particles.count !== want;
    if (fresh) particles.resize(want, spawn);
    // Reduced motion: still trails, pre-run once when spawned and redrawn only on change.
    for (let k = flowSteps(reducedMotion, fresh); k > 0; k--) particles.step(flowField, spawn, gone);
    flowStale = false;
    fctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    fctx.clearRect(0, 0, w, h);
    particles.arrival = intro && !reducedMotion ? intro.arrival : 1;
    particles.draw(fctx, dv, w, h);
    if (!intro) drawMarker(dv, w, h);
  }

  function drawMarker(dv: View, w: number, h: number): void {
    const at = probe.at();
    if (!at) return;
    const p = project(dv, w, h, at.lat, at.lon);
    if (!p.visible) return;
    fctx.beginPath();
    fctx.arc(p.x, p.y, 6, 0, 2 * Math.PI);
    fctx.lineWidth = 2;
    fctx.strokeStyle = "#3fe0ff";
    fctx.stroke();
  }
  requestAnimationFrame(frame);

  let applySeq = 0;
  async function applyHour(): Promise<void> {
    if (!manifest || !store) return;
    const seq = ++applySeq;
    if (layer.shade.kind === "tide") {
      const a = await ensureTide();
      if (seq !== applySeq) return;
      renderer.setTidePhases(phasesAt(a, timeAt(hour)));
      dataReady = true;
      dirty = flowStale = true;
      refreshProbe();
      return;
    }
    const got = await store.ensure(hour);
    if (seq !== applySeq) return; // a newer hour or another layer has been asked for meanwhile
    const p = got[layer.shade.family];
    if (!p) return;
    if (p.fa !== shown.a || p.fb !== shown.b) {
      const veil = layer.id === "rain" && got.b ? { a: got.b.a, b: got.b.b } : undefined;
      renderer.setFrames(p.a, p.b, p.mix, veil);
      shown = { a: p.fa, b: p.fb };
    } else {
      renderer.setMix(p.mix);
    }
    frames = got;
    dataReady = true;
    dirty = flowStale = true;
    refreshProbe();
  }

  void withRetry(() => loadBitmap(`${ASSET_BASE}/land-mask.png`), showNotice).then((img) => {
    renderer.setLandMask(img);
    land = landGridFrom(img);
    landReady = true;
    flowStale = true;
    dirty = true;
  });

  void withRetry(async () => {
    const res = await fetch(`${ASSET_BASE}/coast.json`);
    if (!res.ok) throw new Error(`coast.json: HTTP ${res.status}`);
    return (await res.json()) as { lines: number[][] };
  }, showNotice).then((c) => {
    coast = c.lines;
    dirty = overlayDirty = true;
  });

  async function load(): Promise<void> {
    const lt = await withRetry(() => loadLatest(WX_BASE), showNotice);
    manifest = await withRetry(() => loadManifest(WX_BASE, lt.dir), showNotice);
    latest = lt;
    renderer.setGrid(manifest);
    info = { run: lt.run, cells: manifest.w * manifest.h };
    store = openStore();

    const hours = manifest.hours;
    hour = initialHour(lt.run, new Date(), hours);
    if (opts.timeline) {
      timeline = mountTimeline(opts.timeline, { hours, runIso: lt.run, onHour: (h) => void setHour(h) });
      timeline.setHour(hour);
      // Autoplay unless reduced motion; playback holds while the globe is off screen.
      const t = timeline;
      new IntersectionObserver(([e]) => t.setSuspended(!e.isIntersecting)).observe(root);
      t.setPlaying(!window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    }
    showLegend();
    unitListeners.push((u) => setLegendUnits?.(u));
    await applyHour();
  }

  let setLegendUnits: ((u: Units) => void) | null = null;
  function showLegend(): void {
    setLegendUnits = opts.legend ? mountLegend(opts.legend, layer, units) : null;
  }

  function openStore(): LayerFrames {
    const s = new LayerFrames(WX_BASE, latest!.dir, manifest!, layer.families);
    s.onError = (m) => { if (s === store) showNotice(m); }; // only the live layer drives the notice
    return s;
  }

  async function switchLayer(id: LayerId): Promise<void> {
    if (id === layer.id) return;
    layer = LAYERS[id];
    renderer.setLayer(layer);
    shown = { a: -1, b: -1 };
    frames = null;
    applySeq++; // drop frames still arriving for the previous layer
    particles.resize(0, () => [0, 0]);
    fctx.setTransform(1, 0, 0, 1, 0, 0);
    fctx.clearRect(0, 0, flow.width, flow.height); // no old trails while the new layer loads
    dirty = flowStale = true;
    probe.hide();
    if (!manifest || !latest) return; // load() opens the store with the new layer
    store?.dispose();
    showNotice(null);
    store = openStore();
    showLegend();
    await applyHour();
  }
  // The first failure rejects `loaded` (the splash stops waiting); loading itself keeps retrying.
  handle.loaded = new Promise<void>((resolve, reject) => {
    failLoad = () => reject(new Error(LOAD_NOTICE));
    load().then(resolve, (err) => { console.error(err); reject(err); });
  });
  handle.loaded.catch(() => {});
  return handle;
}
