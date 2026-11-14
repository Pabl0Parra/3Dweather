# Phase 2a: Globe and Wave Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `/wave-map` page showing a draggable, zoomable 3D globe with land, coastlines and the animated wave-height layer read from the phase 1 sprites, with a timeline and deep links.

**Architecture:** The pipeline gains a `static` command that builds the land mask and coastline from Natural Earth, and `build --latest` writes `latest.json`. The web side is an Astro static site; the globe is framework-free TypeScript. Pure modules (view maths, hash, codecs, frame timing, timeline maths, ramp) are unit-tested with Vitest. The WebGL renderer draws sea, land and the wave layer in one fragment shader; a 2D canvas on top draws graticule and coastline. A Playwright smoke test checks real pixels against the reference run.

**Tech Stack:** Python (existing `pipeline`, Pillow); Node 24; Astro 7.4.2; TypeScript 5.9.3; Vitest 4.1.12; @playwright/test 1.64.1. No map or WebGL library.

**Spec:** `docs/superpowers/specs/2026-11-14-same-sources-data-design.md` (sections 5, 7, 10). Behaviour reference: `docs/wave-map-findings-and-plan.md` sections 4-6.

Phase 2b (separate plan): particles, tap readout, "biggest waves", units, Ignition splash.

## Global Constraints

- Write all code fresh. Never copy code, CSS, text or colour values from `reference/thetidechart-capture/`. Numbers about formats (grid, byte encodings, frame layout) are facts and may be used.
- Never fetch from thetidechart.com. Natural Earth comes from `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/` (pinned tag).
- Generated files are never committed: add `web/public/wx/`, `web/public/assets/globe/`, `web/node_modules/`, `web/dist/`, `web/test-results/`, `web/playwright-report/` to `.gitignore`.
- Data URLs come from `import.meta.env.PUBLIC_WX_BASE` (default `/wx`) and `PUBLIC_ASSET_BASE` (default `/assets/globe`).
- Byte decodings must match `pipeline/codecs.py` exactly: height `(b/255)^2 * 16`; vector `(b-128)/127` per axis, x east, y north, pointing where waves travel, length × 25 = period s.
- Globe grid (from `globe.json`, never hard-coded in the renderer): cell (x, y) centre `lon = west + x*dlon`, `lat = north - y*dlat`.
- View: orthographic; radius `R = zoom * 0.45 * min(W - 16, H - 16)` CSS px; zoom clamped to [0.75, 16]; centre latitude clamped to [-85, 85]; longitude wrapped to [-180, 180).
- Canvas device-pixel ratio capped at 2.
- Images are decoded without colour conversion: `createImageBitmap(blob, { colorSpaceConversion: "none", premultiplyAlpha: "none" })`, and WebGL `UNPACK_COLORSPACE_CONVERSION_WEBGL = NONE`, `UNPACK_PREMULTIPLY_ALPHA_WEBGL = false`.
- The page shows the credit line: `Waves: NOAA GFS-Wave via Open-Meteo.com (CC BY 4.0) · Coastlines: Natural Earth`.
- Branch `phase-2a-globe`. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Dev data: `python -m pipeline build --run 2026111306 --cache reference/openmeteo-inputs --out web/public/wx --latest` and `python -m pipeline static --cache reference/naturalearth --out web/public/assets/globe`.

Designer's calls (stated, open to correction):
- Wave colour ramp, ours, ending in the splash accent `#ff4fa3` (metres → RGBA 0-255): 0 → (12,40,80,115) · 1 → (20,90,150,153) · 2 → (30,150,190,184) · 3 → (60,200,170,204) · 4.5 → (220,215,90,217) · 6 → (245,150,50,230) · 9 → (230,60,70,237) · 12 → (255,79,163,242) · 16 → (245,235,255,247). Legend ticks 1, 3, 6, 9, 12 m.
- Colours: page `#03060d`, sea base `#081a2e`, land `#1b2636`, coastline `rgba(140,235,255,0.55)`, graticule `rgba(90,150,210,0.18)`, limb glow cyan `#3fe0ff`.
- Default view `#20,0,1.0`. Timeline speed 1× = 1.5 forecast hours per second; speeds ½×, 1×, 2×.

## Review Focus

1. A sprite file that fails to load → land and coast still draw, a "Couldn't load the forecast, retrying…" notice shows, retries after 2, 4, 8, 16 s.
2. A view centred on the antimeridian (`#0,180,4`) → no visible seam in the wave layer.
3. A malformed or out-of-range hash (`#abc`, `#120,500,99`) → default or clamped view, no exception.
4. A run older than its forecast window (the reference run in 2026-11-14 onward) → timeline starts at hour 0, labels correct, no negative hours.
5. A resize or DPR change → both canvases resize together and stay aligned.

---

### Task 1: Base map assets and `latest.json`

**Files:**
- Create: `pipeline/static_assets.py`, `tests/test_static_assets.py`
- Modify: `pipeline/build.py` (add `write_latest`), `pipeline/__main__.py` (add `static` command and `--latest`), `tests/test_build.py`, `.gitignore`

**Interfaces:**
- Produces:
  - `rasterize_land(geojson: dict, w: int = 2048, h: int = 1024) -> PIL.Image.Image` mode `"L"`, 255 land / 0 sea, x = `(lon + 180) / 360 * w`, y = `(90 - lat) / 180 * h`; polygon holes drawn back as 0
  - `coast_lines(geojson: dict) -> list[list[float]]` flat `[lon, lat, lon, lat, …]` per line, rounded to 2 decimals, consecutive duplicates dropped, lines shorter than 2 points dropped
  - `build_static(cache_dir: Path, out_dir: Path, fetch=http_fetch) -> None` writes `land-mask.png` and `coast.json` = `{"source": "Natural Earth 1:50m v5.1.2 (public domain)", "lines": [...]}`
  - `write_latest(out_dir: Path, run: datetime, built: datetime) -> None` writes `out_dir/latest.json` = `{"run": "2026-11-13T06:00Z", "dir": "2026111306", "built": "<iso Z>"}` via a `.part` file
  - CLI: `python -m pipeline static --cache DIR --out DIR`; `python -m pipeline build … --latest` calls `write_latest` after a successful build

- [ ] **Step 1: Branch** `git checkout -b phase-2a-globe` from up-to-date `main`; add the `.gitignore` lines from Global Constraints.
- [ ] **Step 2: Write the failing tests**

```python
SQUARE_WITH_HOLE = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
    "geometry": {"type": "Polygon", "coordinates": [
        [[-10, -10], [10, -10], [10, 10], [-10, 10], [-10, -10]],
        [[-2, -2], [2, -2], [2, 2], [-2, 2], [-2, -2]]]}}]}

def px(img, lat, lon):
    w, h = img.size
    return img.getpixel((int((lon + 180) / 360 * w), int((90 - lat) / 180 * h)))

def test_land_mask_fills_polygon_and_keeps_holes():
    img = rasterize_land(SQUARE_WITH_HOLE, 360, 180)
    assert img.mode == "L" and img.size == (360, 180)
    assert px(img, 6, 6) == 255 and px(img, 0, 0) == 0 and px(img, 30, 30) == 0

def test_multipolygon_supported(): ...      # two squares as MultiPolygon; both filled

def test_coast_lines_are_flat_rounded_and_deduplicated():
    gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry":
          {"type": "LineString", "coordinates": [[1.234, 5.678], [1.2341, 5.6779], [3, 4]]}},
          {"type": "Feature", "properties": {}, "geometry": {"type": "LineString", "coordinates": [[0, 0]]}}]}
    assert coast_lines(gj) == [[1.23, 5.68, 3.0, 4.0]]

def test_build_static_writes_both_files(tmp_path): ...   # fake fetch serves SQUARE_WITH_HOLE for land and the line above for coast

def test_write_latest(tmp_path):                          # in tests/test_build.py
    write_latest(tmp_path, datetime(2026, 11, 13, 6, tzinfo=timezone.utc), datetime(2026, 11, 14, 9, 30, tzinfo=timezone.utc))
    assert json.loads((tmp_path / "latest.json").read_text()) == {
        "run": "2026-11-13T06:00Z", "dir": "2026111306", "built": "2026-11-14T09:30:00Z"}
```

- [ ] **Step 3: Run** `.venv/Scripts/python -m pytest tests/test_static_assets.py tests/test_build.py -q -m "not reference"` — expected: new tests FAIL (import errors).
- [ ] **Step 4: Implement** `pipeline/static_assets.py` (Pillow `ImageDraw.polygon`; reuse `http_fetch` from `pipeline.sources.openmeteo`; files cached as `<cache>/ne_50m_land.geojson`, `<cache>/ne_50m_coastline.geojson`), `write_latest`, and the CLI changes.
- [ ] **Step 5: Run the tests** — expected: PASS.
- [ ] **Step 6: Generate real assets and check them.** Run the two dev-data commands from Global Constraints. Expected: `land-mask.png` 2048×1024, `coast.json` under 1.5 MB. Spot-check with Pillow: lat 0 lon 20 (Africa) = 255; lat 0 lon −30 (Atlantic) = 0; lat 40.4 lon −3.7 (Madrid) = 255; lat 40 lon −30 = 0.
- [ ] **Step 7: Commit** `feat: Natural Earth land mask and coastline; latest.json pointer`.

### Task 2: Web scaffold, view maths and deep links

**Files:**
- Create: `web/package.json`, `web/astro.config.mjs`, `web/tsconfig.json`, `web/vitest.config.ts`, `web/src/globe/view.ts`, `web/src/globe/hash.ts`, `web/src/globe/view.test.ts`, `web/src/globe/hash.test.ts`

**Interfaces:**
- Produces (`view.ts`):
  - `type View = { lat0: number; lon0: number; zoom: number }`
  - `clampView(v: View): View` — zoom to [0.75, 16], lat0 to [-85, 85], lon0 wrapped to [-180, 180)
  - `radiusPx(zoom: number, w: number, h: number): number`
  - `project(v: View, w: number, h: number, lat: number, lon: number): { x: number; y: number; visible: boolean }` — screen CSS px, y down; `visible` false on the far side
  - `unproject(v: View, w: number, h: number, x: number, y: number): { lat: number; lon: number } | null` — null outside the disk
  - `rotateBy(v: View, dxPx: number, dyPx: number, w: number, h: number): View` — drag: `lon0 -= dx / R` rad, `lat0 += dy / R` rad, clamped
- Produces (`hash.ts`):
  - `parseHash(hash: string): View | null` — `"#lat,lon,zoom"`; null if not three finite numbers; otherwise `clampView`
  - `formatHash(v: View): string` — lat and lon to 2 decimals, zoom to 1: `"#44.50,9.50,2.7"`

- [ ] **Step 1: Scaffold.** `web/package.json` (private, `"type": "module"`), scripts `dev`, `build`, `preview`, `test` (`vitest run`), `e2e` (`playwright test`); exact versions `astro@7.4.2`, `typescript@5.9.3`, `vitest@4.1.12`, `@playwright/test@1.64.1`. Astro `output: "static"`. `npm install` in `web/`.
- [ ] **Step 2: Write the failing tests**

```ts
const V = { lat0: 0, lon0: 0, zoom: 1 }, W = 800, H = 600;
test("centre projects to screen centre", () => {
  expect(project(V, W, H, 0, 0)).toEqual({ x: 400, y: 300, visible: true });
});
test("radius formula", () => { expect(radiusPx(2, 800, 600)).toBeCloseTo(2 * 0.45 * 584); });
test("90 degrees east lands on the right edge; far side invisible", () => {
  const p = project(V, W, H, 0, 90); expect(p.x).toBeCloseTo(400 + radiusPx(1, W, H)); expect(p.y).toBeCloseTo(300);
  expect(project(V, W, H, 0, 180).visible).toBe(false);
});
test("north is up", () => { expect(project(V, W, H, 45, 0).y).toBeLessThan(300); });
test("unproject inverts project on the near side", () => {
  const v = { lat0: 44.5, lon0: 9.5, zoom: 2.7 }; const p = project(v, W, H, 50, 20);
  const q = unproject(v, W, H, p.x, p.y)!; expect(q.lat).toBeCloseTo(50, 6); expect(q.lon).toBeCloseTo(20, 6);
});
test("unproject outside the disk is null", () => { expect(unproject(V, W, H, 5, 5)).toBeNull(); });
test("clampView limits and wraps", () => {
  expect(clampView({ lat0: 120, lon0: 190, zoom: 99 })).toEqual({ lat0: 85, lon0: -170, zoom: 16 });
});
test("dragging right moves the view west", () => { expect(rotateBy(V, 10, 0, W, H).lon0).toBeLessThan(0); });

test("parse and format round trip", () => {
  expect(parseHash("#44.5,9.5,2.7")).toEqual({ lat0: 44.5, lon0: 9.5, zoom: 2.7 });
  expect(formatHash({ lat0: 44.5, lon0: 9.5, zoom: 2.7 })).toBe("#44.50,9.50,2.7");
});
test("bad hashes", () => {
  expect(parseHash("#abc")).toBeNull(); expect(parseHash("")).toBeNull(); expect(parseHash("#1,2")).toBeNull();
  expect(parseHash("#120,500,99")).toEqual({ lat0: 85, lon0: 140, zoom: 16 });
});
```

- [ ] **Step 3: Run** `npm test` in `web/` — expected: FAIL (modules missing).
- [ ] **Step 4: Implement** `view.ts` and `hash.ts` (standard orthographic forward and inverse formulas).
- [ ] **Step 5: Run** `npm test` — expected: 10 passed.
- [ ] **Step 6: Commit** `feat: web scaffold, orthographic view maths and deep links`.

### Task 3: Decoding, frame timing and colour ramp

**Files:**
- Create: `web/src/globe/codecs.ts`, `web/src/globe/manifest.ts`, `web/src/globe/ramp.ts`, and a `.test.ts` beside each

**Interfaces:**
- Produces (`codecs.ts`): `decodeHeight(b: number): number`; `decodeWave(g: number, b: number): { periodS: number; fromDeg: number }` (fromDeg = travel bearing + 180, in [0, 360))
- Produces (`manifest.ts`):
  - `type Latest = { run: string; dir: string; built: string }`
  - `type GlobeManifest = { run: string; w: number; h: number; north: number; west: number; dlon: number; dlat: number; every: number; hours: number; frames: number; cols: number; chunks: number[]; sources: Record<string, string>; peaks: Record<string, [number, number, number][]> }`
  - `loadLatest(base: string): Promise<Latest>`; `loadManifest(base: string, dir: string): Promise<GlobeManifest>` (plain `fetch`, throw on non-OK)
  - `framePair(m: GlobeManifest, hour: number): { a: number; b: number; mix: number }` — hour clamped to [0, hours]
  - `chunkSlot(m: GlobeManifest, frame: number): { chunk: number; slot: number }`
- Produces (`ramp.ts`): `RAMP_STOPS: [number, [number, number, number, number]][]` (the designer's ramp above); `rampTable(): Uint8Array` — 256 × RGBA indexed **by the height byte** (entry i = colour at `decodeHeight(i)` metres, linear between stops); `LEGEND_TICKS = [1, 3, 6, 9, 12]`

- [ ] **Step 1: Write the failing tests**

```ts
test("height byte 237 is 13.82 m", () => { expect(decodeHeight(237)).toBeCloseTo(13.82, 2); });
test("waves travelling east come from the west, period from length", () => {
  const w = decodeWave(179, 128); expect(w.fromDeg).toBeCloseTo(270, 0); expect(w.periodS).toBeCloseTo(10.0, 1);
});
test("travelling south means from north", () => { expect(decodeWave(128, 1).fromDeg).toBeCloseTo(0, 0); });

const M = { every: 3, hours: 168, frames: 57, chunks: [8, 8, 8, 8, 8, 8, 9] } as GlobeManifest;
test("frame pairs", () => {
  expect(framePair(M, 0)).toEqual({ a: 0, b: 1, mix: 0 });
  expect(framePair(M, 4.5)).toEqual({ a: 1, b: 2, mix: 0.5 });
  expect(framePair(M, 168)).toEqual({ a: 56, b: 56, mix: 0 });
  expect(framePair(M, -5)).toEqual({ a: 0, b: 1, mix: 0 });
});
test("chunk slots", () => {
  expect(chunkSlot(M, 7)).toEqual({ chunk: 0, slot: 7 }); expect(chunkSlot(M, 48)).toEqual({ chunk: 6, slot: 0 });
  expect(chunkSlot(M, 56)).toEqual({ chunk: 6, slot: 8 });
});

test("ramp table endpoints and a stop", () => {
  const t = rampTable(); expect(t.length).toBe(1024);
  expect([...t.slice(0, 4)]).toEqual([12, 40, 80, 115]);
  expect([...t.slice(1020, 1024)]).toEqual([245, 235, 255, 247]);
  const i = 64; // decodeHeight(64) ≈ 1.0 m
  expect(Math.abs(t[i * 4] - 20)).toBeLessThanOrEqual(1);
});
```

- [ ] **Step 2: Run** `npm test` — expected: FAIL (modules missing).
- [ ] **Step 3: Implement** the three modules.
- [ ] **Step 4: Run** `npm test` — expected: all passed.
- [ ] **Step 5: Commit** `feat: wave decoding, frame timing and colour ramp`.

### Task 4: Sprite loader

**Files:**
- Create: `web/src/globe/frames.ts`, `web/src/globe/frames.test.ts`

**Interfaces:**
- Consumes: `GlobeManifest`, `chunkSlot`.
- Produces:
  - `RETRY_DELAYS_MS = [2000, 4000, 8000, 16000]`
  - `chunksToKeep(current: number, count: number): number[]` → `[current, current + 1]` without going past the last chunk
  - `class FrameStore(base: string, dir: string, family: "w", m: GlobeManifest, opts?: { fetchImpl?: typeof fetch; sleep?: (ms: number) => Promise<void>; decode?: (blob: Blob) => Promise<ImageData> })` — `decode` defaults to the browser path below; tests inject a fake
    - `ensure(frame: number): Promise<void>` — loads that frame's chunk and the next; drops others
    - `pixels(frame: number): Uint8ClampedArray | null` — RGBA 768×384 of that frame, or null if not loaded
    - `onError: (message: string | null) => void` — called with the notice text while retrying, and `null` on success
  - Loading: `fetch` → `blob` → `createImageBitmap` (no colour conversion, see Global Constraints) → `OffscreenCanvas` `getImageData` once per chunk; slice frames lazily. On failure retry after each delay in `RETRY_DELAYS_MS`, then keep failing with the last delay.

- [ ] **Step 1: Write the failing tests** (Vitest; `fetchImpl`, `sleep` and `decode` injected)

```ts
test("keeps current and next chunk only", () => {
  expect(chunksToKeep(0, 7)).toEqual([0, 1]); expect(chunksToKeep(6, 7)).toEqual([6]);
});
test("slices a frame out of its chunk", async () => { ... });   // fake 3072x768 ImageData where frame 5 is filled with value 5; pixels(5)[0] === 5
test("retries with the backoff schedule and reports the notice", async () => { ... });
  // fetch fails 3 times then succeeds; recorded sleeps === [2000, 4000, 8000]; onError got the notice then null
test("returns null for a frame not yet loaded", () => { ... });
```

- [ ] **Step 2: Run** `npm test` — expected: FAIL.
- [ ] **Step 3: Implement** `frames.ts` (with the `decode` option defaulting to the real browser path).
- [ ] **Step 4: Run** `npm test` — expected: all passed.
- [ ] **Step 5: Commit** `feat: sprite loader with chunk window and retries`.

### Task 5: WebGL globe, page and pixel smoke test

**Files:**
- Create: `web/src/globe/renderer.ts`, `web/src/globe/globe.ts`, `web/src/pages/wave-map.astro`, `web/src/styles/globe.css`, `web/playwright.config.ts`, `web/tests/e2e/globe.spec.ts`

**Interfaces:**
- Consumes: `View`, `radiusPx`, `GlobeManifest`, `FrameStore.pixels`, `rampTable`, `framePair`.
- Produces:
  - `class GlobeRenderer(canvas: HTMLCanvasElement)` — `setLandMask(img: ImageBitmap)`, `setFrames(a: Uint8ClampedArray, b: Uint8ClampedArray, mix: number)`, `setMix(mix: number)`, `draw(v: View, cssW: number, cssH: number, dpr: number)`
  - `initGlobe(root: HTMLElement): Promise<GlobeHandle>` with `GlobeHandle = { ready: boolean; view(): View; setView(v: View): void; hour(): number; setHour(h: number): void }` (`ready` turns true after the first frame with wave data is drawn); also exposed as `window.__globe` when `import.meta.env.DEV` or `?debug` is present (for tests)

Renderer rules:
- One full-screen triangle; the fragment shader inverse-projects each pixel (same formulas as `view.ts`), discards outside the disk.
- Frame textures are 768×384 RGBA, `NEAREST` + `CLAMP_TO_EDGE` (768 is not a power of two). The shader does its own bilinear sampling with 4 fetches per frame and **wraps the x index**, so there is no seam at ±180° (Review Focus 2). Texture coordinate of cell (x, y) centre: `((x + 0.5) / w, (y + 0.5) / h)`; the shader maps lon/lat to fractional cell indices with the manifest's `west, dlon, north, dlat` (uniforms).
- Height byte is mixed between frame A and B with `uMix`, then looked up in the 256×1 ramp texture (`rampTable()`), alpha-blended over the sea base colour. Land (mask > 0.5, `LINEAR`, `REPEAT`; 2048 is a power of two) is drawn in the land colour and gets no wave colour.
- A thin cyan limb glow at the disk edge.
- `preserveDrawingBuffer: true` (needed for the pixel test; revisit in phase 7 polish).

`globe.ts` (this task): read view from the hash or default; load `latest.json`, the manifest, `land-mask.png`, and frames for hour 0; draw on `requestAnimationFrame` only when something changed; resize both canvases on `ResizeObserver` with DPR capped at 2 (Review Focus 5); show the retry notice from `FrameStore.onError` (Review Focus 1). The page holds the credit line and a `<noscript>` text.

- [ ] **Step 1: Write the smoke test** (skipped with a clear reason when `web/public/wx/latest.json` is absent; Playwright runs `npm run build && npm run preview` on port 4321)

```ts
test("open sea at the reference peak shows the top of the ramp", async ({ page }) => {
  await page.goto("/wave-map?debug#44.28,-140.92,4");
  await page.waitForFunction(() => (window as any).__globe?.ready === true);
  const [r, g, b] = await centrePixel(page);           // reads the WebGL canvas centre
  expect(r).toBeGreaterThan(200); expect(b).toBeGreaterThan(120); expect(g).toBeLessThan(140); // 13.8 m, pink end
});
test("land is drawn in the land colour", async ({ page }) => { ... });   // #40.4,-3.7,4 → within 12 of (27,38,54)
test("no seam at the antimeridian", async ({ page }) => { ... });     // #0,180,4: |pixel(cx-2) - pixel(cx+2)| ≤ 6 per channel
test("a failed sprite shows the retry notice and still draws land", async ({ page }) => { ... });
  // route **/globe-w0.webp → abort; notice text "Couldn't load the forecast" visible; land pixel check passes
test("no console errors on load", async ({ page }) => { ... });
```

- [ ] **Step 2: Run** `npx playwright install chromium` then `npm run e2e` — expected: FAIL (page missing).
- [ ] **Step 3: Implement** `renderer.ts`, `globe.ts`, the page and its CSS.
- [ ] **Step 4: Run** `npm test && npm run e2e` — expected: all passed.
- [ ] **Step 5: Look at it.** Take a screenshot at `#44.5,9.5,2.7` and at `#20,0,1` into the workspace and check by eye: dark sea, wave colours over the ocean, land shapes correct, no seam. Note anything odd in the ledger.
- [ ] **Step 6: Commit** `feat: WebGL globe with land and wave layer`.

### Task 6: Coastline overlay, gestures and hash sync

**Files:**
- Create: `web/src/globe/overlay.ts`, `web/src/globe/gestures.ts`, `web/src/globe/overlay.test.ts`, `web/src/globe/gestures.test.ts`
- Modify: `web/src/globe/globe.ts`, `web/tests/e2e/globe.spec.ts`

**Interfaces:**
- Consumes: `project`, `unproject`, `rotateBy`, `clampView`, `formatHash`.
- Produces:
  - `visibleRuns(v: View, w: number, h: number, flat: number[]): [number, number][][]` — the screen points of one coast line, split wherever it crosses to the far side
  - `drawOverlay(ctx: CanvasRenderingContext2D, v: View, w: number, h: number, coast: number[][]): void` — graticule every 30° then coastline
  - `stepInertia(vel: { x: number; y: number }): { x: number; y: number } | null` — multiplies by 0.92, null once both |components| < 0.01 px/frame
  - `zoomBy(v: View, factor: number): View` (clamped)
  - `attachGestures(el: HTMLElement, get: () => View, set: (v: View) => void, size: () => { w: number; h: number }): () => void` — drag with inertia; pinch; double-click = centre on that point and zoom ×2; keys ←→↑↓ (5°), `+`/`-` (×1.25); wheel zooms **only after the map has been clicked** (cooperative), otherwise the page scrolls and a hint "Click the map to zoom with the wheel" shows for 1.5 s

`globe.ts`: load `coast.json`; redraw the overlay only when the view changes; rewrite the hash with `history.replaceState` 600 ms after the view stops changing.

- [ ] **Step 1: Write the failing tests**

```ts
test("a line crossing the horizon is split into near-side runs", () => {
  const runs = visibleRuns({ lat0: 0, lon0: 0, zoom: 1 }, 800, 600, [60, 0, 80, 0, 100, 0, 120, 0]);
  expect(runs.length).toBe(1); expect(runs[0].length).toBe(2);
});
test("inertia decays and stops", () => {
  let v: any = { x: 10, y: 0 }, n = 0; while ((v = stepInertia(v))) n++;
  expect(n).toBeGreaterThan(75); expect(n).toBeLessThan(90);   // 10 · 0.92^n < 0.01 at n ≈ 83
});
test("zoomBy clamps", () => { expect(zoomBy({ lat0: 0, lon0: 0, zoom: 15 }, 2).zoom).toBe(16); });
```

Add to the smoke test: a mouse drag of 200 px to the right changes `location.hash` longitude to a smaller value within 1.5 s; a wheel event before any click leaves the zoom unchanged.

- [ ] **Step 2: Run** `npm test` — expected: FAIL.
- [ ] **Step 3: Implement** `overlay.ts`, `gestures.ts`, wire into `globe.ts`.
- [ ] **Step 4: Run** `npm test && npm run e2e` — expected: all passed.
- [ ] **Step 5: Commit** `feat: coastline overlay, gestures and hash sync`.

### Task 7: Timeline, playback and legend

**Files:**
- Create: `web/src/globe/timeline.ts`, `web/src/globe/timeline.test.ts`, `web/src/globe/ui.ts`
- Modify: `web/src/globe/globe.ts`, `web/src/pages/wave-map.astro`, `web/src/styles/globe.css`, `web/tests/e2e/globe.spec.ts`

**Interfaces:**
- Consumes: `framePair`, `FrameStore.ensure/pixels`, `GlobeRenderer.setFrames/setMix`, `LEGEND_TICKS`, `RAMP_STOPS`.
- Produces:
  - `SPEEDS = [0.5, 1, 2]`; `HOURS_PER_SECOND = 1.5`
  - `initialHour(runIso: string, now: Date, hours: number): number` — `(now − run)` in hours, clamped to [0, hours] (Review Focus 4)
  - `advance(hour: number, dtSeconds: number, speed: number, hours: number): number` — wraps to 0 after `hours`
  - `timeLabel(runIso: string, hour: number, now: Date, timeZone?: string): string` — `"Fri 13 Nov, 18:00 · in 12 h"`; "now" when within ±0.5 h; "12 h ago" in the past; hours rounded to whole hours below 48 h, then `Math.round(h / 24)` days ("in 3 days"); appends `" · less certain"` beyond hour 120
  - `mountTimeline(root: HTMLElement, opts: { hours: number; runIso: string; onHour: (h: number) => void }): { setHour(h: number): void; setPlaying(p: boolean): void }` — slider 0…hours step 0.05, day ticks at local midnights, a "now" marker, play/pause, speed button cycling ½×/1×/2×, Space toggles play
  - `mountLegend(root: HTMLElement): void` — gradient from `RAMP_STOPS` with ticks 1, 3, 6, 9, 12 m

`globe.ts`: when the hour changes, `ensure` the needed frames, upload a new pair only when `a`/`b` change, otherwise only `setMix`. Autoplay is off when `prefers-reduced-motion: reduce`; playback pauses when the globe is off-screen (`IntersectionObserver`).

- [ ] **Step 1: Write the failing tests**

```ts
const RUN = "2026-11-13T06:00Z";
test("initial hour clamps", () => {
  expect(initialHour(RUN, new Date("2026-11-13T18:00Z"), 168)).toBe(12);
  expect(initialHour(RUN, new Date("2026-11-30T00:00Z"), 168)).toBe(168);
  expect(initialHour(RUN, new Date("2026-11-01T00:00Z"), 168)).toBe(0);
});
test("advance wraps", () => {
  expect(advance(10, 2, 1, 168)).toBeCloseTo(13); expect(advance(167, 2, 1, 168)).toBeCloseTo(0);
});
test("labels", () => {
  const now = new Date("2026-11-13T06:00Z");
  expect(timeLabel(RUN, 12, now, "UTC")).toBe("Fri 13 Nov, 18:00 · in 12 h");
  expect(timeLabel(RUN, 0, now, "UTC")).toBe("Fri 13 Nov, 06:00 · now");
  expect(timeLabel(RUN, 72, now, "UTC")).toBe("Mon 16 Nov, 06:00 · in 3 days");
  expect(timeLabel(RUN, 126, now, "UTC")).toBe("Wed 18 Nov, 12:00 · in 5 days · less certain");
});
```

Add to the smoke test: pressing Space starts playback and the slider value increases within 2 s; at `?debug` `__globe.setHour(4.5)` then the centre pixel at the reference peak differs from hour 0 (frames blend).

- [ ] **Step 2: Run** `npm test` — expected: FAIL.
- [ ] **Step 3: Implement** `timeline.ts`, `ui.ts`, wire into `globe.ts` and the page.
- [ ] **Step 4: Run** the whole suite: `npm test && npm run e2e` in `web/`, and `.venv/Scripts/python -m pytest -q -m "not reference"` at the root — expected: all passed.
- [ ] **Step 5: Look at it.** Screenshots at hour 0 and hour 90 into the workspace; check the timeline label, legend and that waves moved.
- [ ] **Step 6: Commit** `feat: timeline, playback and legend`.
