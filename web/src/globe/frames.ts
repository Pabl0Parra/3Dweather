// Loads sprite chunks and hands out single frames as RGBA pixels.
import { chunkSlot, type GlobeManifest } from "./manifest";

export const RETRY_DELAYS_MS = [2000, 4000, 8000, 16000];
export const LOAD_NOTICE = "Couldn't load the forecast, retrying…";

export function chunksToKeep(current: number, count: number): number[] {
  return current + 1 < count ? [current, current + 1] : [current];
}

/** Browser path: decode without colour conversion so the bytes stay exact. */
async function decodeImage(blob: Blob): Promise<ImageData> {
  const bitmap = await createImageBitmap(blob, { colorSpaceConversion: "none", premultiplyAlpha: "none" });
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

type Opts = {
  fetchImpl?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
  decode?: (blob: Blob) => Promise<ImageData>;
};

export class FrameStore {
  onError: (message: string | null) => void = () => {};
  private chunks = new Map<number, ImageData>();
  private pending = new Map<number, Promise<void>>();
  private frameCache = new Map<number, Uint8ClampedArray>();
  private fetchImpl: typeof fetch;
  private sleep: (ms: number) => Promise<void>;
  private decode: (blob: Blob) => Promise<ImageData>;

  constructor(private base: string, private dir: string, private family: "w", private m: GlobeManifest, opts: Opts = {}) {
    this.fetchImpl = opts.fetchImpl ?? ((...a) => fetch(...a));
    this.sleep = opts.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.decode = opts.decode ?? decodeImage;
  }

  /**
   * Wait for the chunks holding `frame` and `also` (which may be in the next chunk);
   * prefetch the next chunk without waiting for it; forget the rest.
   */
  async ensure(frame: number, also: number = frame): Promise<void> {
    const keep = chunksToKeep(chunkSlot(this.m, frame).chunk, this.m.chunks.length);
    for (const c of [...this.chunks.keys()]) if (!keep.includes(c)) this.drop(c);
    const need = new Set([chunkSlot(this.m, frame).chunk, chunkSlot(this.m, also).chunk]);
    const loads = [...need].map((c) => this.load(c));
    for (const c of keep) if (!need.has(c)) void this.load(c);
    await Promise.all(loads);
  }

  pixels(frame: number): Uint8ClampedArray | null {
    const cached = this.frameCache.get(frame);
    if (cached) return cached;
    const { chunk, slot } = chunkSlot(this.m, frame);
    const img = this.chunks.get(chunk);
    if (!img) return null;
    const { w, h, cols } = this.m;
    const out = new Uint8ClampedArray(w * h * 4);
    const x0 = (slot % cols) * w, y0 = Math.floor(slot / cols) * h;
    for (let y = 0; y < h; y++) {
      const start = ((y0 + y) * img.width + x0) * 4;
      out.set(img.data.subarray(start, start + w * 4), y * w * 4);
    }
    this.frameCache.set(frame, out);
    return out;
  }

  private drop(chunk: number): void {
    this.chunks.delete(chunk);
    for (const f of [...this.frameCache.keys()]) if (chunkSlot(this.m, f).chunk === chunk) this.frameCache.delete(f);
  }

  private load(chunk: number): Promise<void> {
    if (this.chunks.has(chunk)) return Promise.resolve();
    let p = this.pending.get(chunk);
    if (!p) {
      p = this.fetchWithRetry(chunk).finally(() => this.pending.delete(chunk));
      this.pending.set(chunk, p);
    }
    return p;
  }

  private async fetchWithRetry(chunk: number): Promise<void> {
    const url = `${this.base}/${this.dir}/globe-${this.family}${chunk}.webp`;
    for (let attempt = 0; ; attempt++) {
      try {
        const res = await this.fetchImpl(url);
        if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
        this.chunks.set(chunk, await this.decode(await res.blob()));
        if (attempt > 0) this.onError(null);
        return;
      } catch {
        this.onError(LOAD_NOTICE);
        await this.sleep(RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)]);
      }
    }
  }
}
