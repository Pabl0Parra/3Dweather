import { expect, test } from "vitest";
import { chunksToKeep, FrameStore, RETRY_DELAYS_MS } from "./frames";
import type { GlobeManifest } from "./manifest";

const M = { w: 768, h: 384, cols: 4, every: 3, hours: 168, frames: 57, chunks: [8, 8, 8, 8, 8, 8, 9] } as GlobeManifest;

/** A chunk image where every pixel of frame slot s has R = s and G = chunk index. */
function fakeChunk(chunk: number): ImageData {
  const n = M.chunks[chunk];
  const rows = Math.ceil(n / M.cols);
  const width = M.cols * M.w, height = rows * M.h;
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      const slot = Math.floor(y / M.h) * M.cols + Math.floor(x / M.w);
      const i = (y * width + x) * 4;
      data[i] = slot; data[i + 1] = chunk; data[i + 3] = 255;
    }
  return { data, width, height, colorSpace: "srgb" } as ImageData;
}

function okFetch(urls: string[]): typeof fetch {
  return (async (url: string) => {
    urls.push(url);
    return new Response(new Blob([url]));
  }) as unknown as typeof fetch;
}

async function decodeFromUrl(blob: Blob): Promise<ImageData> {
  const url = await blob.text();
  return fakeChunk(Number(url.match(/globe-w(\d)\.webp/)![1]));
}

test("keeps current and next chunk only", () => {
  expect(chunksToKeep(0, 7)).toEqual([0, 1]);
  expect(chunksToKeep(6, 7)).toEqual([6]);
});

test("slices a frame out of its chunk", async () => {
  const urls: string[] = [];
  const store = new FrameStore("/wx", "2026111306", "w", M, { fetchImpl: okFetch(urls), decode: decodeFromUrl });
  await store.ensure(13); // chunk 1, slot 5
  const px = store.pixels(13)!;
  expect(px.length).toBe(768 * 384 * 4);
  expect([px[0], px[1]]).toEqual([5, 1]);
  expect([px[px.length - 4], px[px.length - 3]]).toEqual([5, 1]);
  expect(urls).toEqual(["/wx/2026111306/globe-w1.webp", "/wx/2026111306/globe-w2.webp"]);
});

test("returns null for a frame not yet loaded", () => {
  const store = new FrameStore("/wx", "d", "w", M, { fetchImpl: okFetch([]), decode: decodeFromUrl });
  expect(store.pixels(0)).toBeNull();
});

test("drops chunks outside the window", async () => {
  const store = new FrameStore("/wx", "d", "w", M, { fetchImpl: okFetch([]), decode: decodeFromUrl });
  await store.ensure(0);
  await store.ensure(30); // chunk 3
  expect(store.pixels(0)).toBeNull();
  expect(store.pixels(30)).not.toBeNull();
});

test("retries with the backoff schedule and reports the notice", async () => {
  let failures = 3;
  const sleeps: number[] = [];
  const notices: (string | null)[] = [];
  const fetchImpl = (async (url: string) => {
    if (url.endsWith("globe-w0.webp") && failures-- > 0) throw new TypeError("network down");
    return new Response(new Blob([url]));
  }) as unknown as typeof fetch;
  const store = new FrameStore("/wx", "d", "w", M, {
    fetchImpl, decode: decodeFromUrl, sleep: async (ms) => { sleeps.push(ms); },
  });
  store.onError = (m) => notices.push(m);
  await store.ensure(0);
  expect(sleeps).toEqual(RETRY_DELAYS_MS.slice(0, 3));
  expect(notices[0]).toMatch(/Couldn't load the forecast/);
  expect(notices[notices.length - 1]).toBeNull();
  expect(store.pixels(0)).not.toBeNull();
});

test("ensure does not wait for the next chunk's prefetch", async () => {
  // Chunk 2 never arrives; frame 13 (chunk 1) must still be served.
  const fetchImpl = (async (url: string) =>
    url.includes("globe-w2") ? new Promise<Response>(() => {}) : new Response(new Blob([url]))) as unknown as typeof fetch;
  const store = new FrameStore("/wx", "d", "w", M, { fetchImpl, decode: decodeFromUrl });
  const done = await Promise.race([store.ensure(13).then(() => "done"), new Promise((r) => setTimeout(() => r("stuck"), 200))]);
  expect(done).toBe("done");
  expect(store.pixels(13)).not.toBeNull();
});

test("ensure can also wait for a second frame in the next chunk", async () => {
  const store = new FrameStore("/wx", "d", "w", M, { fetchImpl: okFetch([]), decode: decodeFromUrl });
  await store.ensure(15, 16); // last of chunk 1, first of chunk 2
  expect(store.pixels(15)).not.toBeNull();
  expect(store.pixels(16)).not.toBeNull();
});
