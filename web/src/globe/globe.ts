// Mounts the globe: canvases, data loading, view state and the draw loop.
import { landGridFrom, sampleWave, type LandGrid } from "./field";
import { particleCount, Particles, spawnOnDisk, TRAIL } from "./particles";
import { FrameStore, RETRY_DELAYS_MS, LOAD_NOTICE } from "./frames";
import { attachGestures } from "./gestures";
import { formatHash, parseHash } from "./hash";
import { drawOverlay } from "./overlay";
import { initialHour, mountTimeline, type TimelineHandle } from "./timeline";
import { formatCoord, Probe, readoutLines } from "./probe";
import { mountLegend } from "./ui";
import { loadUnits, mountUnitsMenu, type Units } from "./units";
import { framePair, loadLatest, loadManifest, type GlobeManifest } from "./manifest";
import { GlobeRenderer } from "./renderer";
import { clampView, project, radiusPx, unproject, type View } from "./view";

export type GlobeHandle = {
  ready: boolean;
  drawn: boolean;
  view(): View;
  setView(v: View): void;
  hour(): number;
  setHour(h: number): Promise<void>;
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
  opts: { timeline?: HTMLElement; legend?: HTMLElement; unitsButton?: HTMLButtonElement } = {},
): Promise<GlobeHandle | null> {
  const canvas = document.createElement("canvas");
  canvas.className = "globe-gl";
  canvas.setAttribute("aria-hidden", "true");
  const notice = document.createElement("p");
  notice.className = "globe-notice";
  notice.setAttribute("role", "status");
  notice.hidden = true;
  root.append(canvas, notice);
  const showNotice = (m: string | null) => {
    notice.textContent = m ?? "";
    notice.hidden = m === null;
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
    msg.textContent = "The wave map needs WebGL, which this browser or device isn't providing.";
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
  let store: FrameStore | null = null;
  let shown = { a: -1, b: -1 };
  // CPU copies for particles, the probe and the peak search.
  let pair: { a: Uint8ClampedArray; b: Uint8ClampedArray; mix: number } | null = null;
  let land: LandGrid | null = null;
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
  };
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
    if (land?.isLand(lat, lon)) lines = readoutLines(null, lat, lon, units);
    else if (!pair || !manifest) lines = ["Forecast still loading…", formatCoord(lat, lon)];
    else lines = readoutLines(sampleWave(pair.a, pair.b, pair.mix, manifest, lat, lon), lat, lon, units);
    probe.show(lat, lon, lines);
  }
  function probeAt(lat: number, lon: number): void {
    probe.show(lat, lon, []);
    refreshProbe();
    flowStale = true;
  }
  unitListeners.push(() => refreshProbe());

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
      renderer.draw(view, w, h, dpr);
      // Both canvases share one size and DPR so they stay aligned.
      const ow = Math.round(w * dpr), oh = Math.round(h * dpr);
      if (overlay.width !== ow || overlay.height !== oh) { overlay.width = ow; overlay.height = oh; overlayDirty = true; }
      if (overlayDirty) {
        overlayDirty = false;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        drawOverlay(ctx, view, w, h, coast);
      }
      if (landReady) handle.drawn = true;
      if (landReady && dataReady) handle.ready = true;
    }
    drawFlow();
    requestAnimationFrame(frame);
  };

  function waveField(lat: number, lon: number) {
    if (!pair || !manifest || !land || land.isLand(lat, lon)) return null;
    const s = sampleWave(pair.a, pair.b, pair.mix, manifest, lat, lon);
    return { u: s.u, v: s.v };
  }

  function drawFlow(): void {
    const w = root.clientWidth, h = root.clientHeight;
    const dpr = Math.min(coarse ? 1.25 : 2, window.devicePixelRatio || 1);
    const fw = Math.round(w * dpr), fh = Math.round(h * dpr);
    if (flow.width !== fw || flow.height !== fh) { flow.width = fw; flow.height = fh; flowStale = true; }
    if (!pair || !land || !onScreen || document.hidden) return;
    if (reducedMotion && !flowStale) return;
    const r = radiusPx(view.zoom, w, h);
    const want = particleCount(Math.min(Math.PI * r * r, w * h), w);
    const spawn = () => spawnOnDisk(view, w, h, land, Math.random);
    const gone = (lat: number, lon: number) => {
      if (Math.abs(lat) > 88) return true;
      const p = project(view, w, h, lat, lon);
      return !p.visible || p.x < -20 || p.y < -20 || p.x > w + 20 || p.y > h + 20;
    };
    if (particles.count !== want) particles.resize(want, spawn);
    // Reduced motion: pre-run a full trail and draw it once, without animating.
    for (let k = reducedMotion ? TRAIL : 1; k > 0; k--) particles.step(waveField, spawn, gone);
    flowStale = false;
    fctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    fctx.clearRect(0, 0, w, h);
    particles.draw(fctx, view, w, h);
    drawMarker(w, h);
  }

  function drawMarker(w: number, h: number): void {
    const at = probe.at();
    if (!at) return;
    const p = project(view, w, h, at.lat, at.lon);
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
    const fp = framePair(manifest, hour);
    await store.ensure(fp.a, fp.b);
    if (seq !== applySeq) return; // a newer hour has been asked for meanwhile
    if (fp.a !== shown.a || fp.b !== shown.b) {
      const a = store.pixels(fp.a), b = store.pixels(fp.b);
      if (!a || !b) return;
      renderer.setFrames(a, b, fp.mix);
      shown = { a: fp.a, b: fp.b };
      pair = { a, b, mix: fp.mix };
    } else {
      renderer.setMix(fp.mix);
      if (pair) pair.mix = fp.mix;
    }
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

  const latest = await withRetry(() => loadLatest(WX_BASE), showNotice);
  manifest = await withRetry(() => loadManifest(WX_BASE, latest.dir), showNotice);
  renderer.setGrid(manifest);
  store = new FrameStore(WX_BASE, latest.dir, "w", manifest);
  store.onError = showNotice;

  const hours = manifest.hours;
  hour = initialHour(latest.run, new Date(), hours);
  if (opts.timeline) {
    timeline = mountTimeline(opts.timeline, { hours, runIso: latest.run, onHour: (h) => void setHour(h) });
    timeline.setHour(hour);
    // Autoplay unless reduced motion; playback holds while the globe is off screen.
    const t = timeline;
    new IntersectionObserver(([e]) => t.setSuspended(!e.isIntersecting)).observe(root);
    t.setPlaying(!window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }
  const setLegendUnit = opts.legend ? mountLegend(opts.legend, units.length) : null;
  unitListeners.push((u) => setLegendUnit?.(u.length));
  await applyHour();
  return handle;
}
