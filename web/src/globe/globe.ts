// Mounts the globe: canvases, data loading, view state and the draw loop.
import { FrameStore, RETRY_DELAYS_MS, LOAD_NOTICE } from "./frames";
import { parseHash } from "./hash";
import { framePair, loadLatest, loadManifest, type GlobeManifest } from "./manifest";
import { GlobeRenderer } from "./renderer";
import { clampView, type View } from "./view";

export type GlobeHandle = {
  ready: boolean;
  drawn: boolean;
  view(): View;
  setView(v: View): void;
  hour(): number;
  setHour(h: number): void;
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

export async function initGlobe(root: HTMLElement): Promise<GlobeHandle> {
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

  const renderer = new GlobeRenderer(canvas);
  let view = parseHash(location.hash) ?? DEFAULT_VIEW;
  let hour = 0;
  let dirty = true;
  let landReady = false;
  let dataReady = false;
  let manifest: GlobeManifest | null = null;
  let store: FrameStore | null = null;
  let shown = { a: -1, b: -1 };

  const handle: GlobeHandle = {
    ready: false,
    drawn: false,
    view: () => view,
    setView: (v) => { view = clampView(v); dirty = true; },
    hour: () => hour,
    setHour: (h) => { hour = h; void applyHour(); },
  };
  if (import.meta.env.DEV || new URLSearchParams(location.search).has("debug")) (window as any).__globe = handle;

  new ResizeObserver(() => { dirty = true; }).observe(root);

  const frame = () => {
    if (dirty) {
      dirty = false;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      renderer.draw(view, root.clientWidth, root.clientHeight, dpr);
      if (landReady) handle.drawn = true;
      if (landReady && dataReady) handle.ready = true;
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);

  async function applyHour(): Promise<void> {
    if (!manifest || !store) return;
    const pair = framePair(manifest, hour);
    await store.ensure(pair.a);
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

  const latest = await withRetry(() => loadLatest(WX_BASE), showNotice);
  manifest = await withRetry(() => loadManifest(WX_BASE, latest.dir), showNotice);
  renderer.setGrid(manifest);
  store = new FrameStore(WX_BASE, latest.dir, "w", manifest);
  store.onError = showNotice;
  await applyHour();
  return handle;
}
