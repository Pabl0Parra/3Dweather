// Mounts the globe: canvases, data loading, view state and the draw loop.
import { FrameStore, RETRY_DELAYS_MS, LOAD_NOTICE } from "./frames";
import { attachGestures } from "./gestures";
import { formatHash, parseHash } from "./hash";
import { drawOverlay } from "./overlay";
import { initialHour, mountTimeline, type TimelineHandle } from "./timeline";
import { mountLegend } from "./ui";
import { framePair, loadLatest, loadManifest, type GlobeManifest } from "./manifest";
import { GlobeRenderer } from "./renderer";
import { clampView, type View } from "./view";

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
  opts: { timeline?: HTMLElement; legend?: HTMLElement } = {},
): Promise<GlobeHandle> {
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

  const renderer = new GlobeRenderer(canvas);
  let view = parseHash(location.hash) ?? DEFAULT_VIEW;
  let hour = 0;
  let dirty = true;
  let overlayDirty = true;
  let landReady = false;
  let dataReady = false;
  let manifest: GlobeManifest | null = null;
  let store: FrameStore | null = null;
  let shown = { a: -1, b: -1 };

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
    dirty = overlayDirty = true;
    clearTimeout(hashTimer);
    hashTimer = window.setTimeout(() => history.replaceState(null, "", formatHash(view)), 600);
  }
  window.addEventListener("hashchange", () => {
    const v = parseHash(location.hash);
    if (v) { view = v; dirty = overlayDirty = true; }
  });

  new ResizeObserver(() => { dirty = overlayDirty = true; }).observe(root);
  attachGestures(root, () => view, setView, () => ({ w: root.clientWidth, h: root.clientHeight }));

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
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);

  let applySeq = 0;
  async function applyHour(): Promise<void> {
    if (!manifest || !store) return;
    const seq = ++applySeq;
    const pair = framePair(manifest, hour);
    await store.ensure(pair.a);
    if (seq !== applySeq) return; // a newer hour has been asked for meanwhile
    if (pair.a !== shown.a || pair.b !== shown.b) {
      const a = store.pixels(pair.a), b = store.pixels(pair.b);
      if (!a || !b) return;
      renderer.setFrames(a, b, pair.mix);
      shown = { a: pair.a, b: pair.b };
    } else {
      renderer.setMix(pair.mix);
    }
    dataReady = true;
    dirty = true;
  }

  void withRetry(() => loadBitmap(`${ASSET_BASE}/land-mask.png`), showNotice).then((img) => {
    renderer.setLandMask(img);
    landReady = true;
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
  if (opts.legend) mountLegend(opts.legend);
  await applyHour();
  return handle;
}
