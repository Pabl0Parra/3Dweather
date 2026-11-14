# Phase 2b: Particles, Probe, Biggest Waves, Units and the Ignition Splash — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the wave globe: particle trails that run the way waves travel, a tap readout, a "Biggest waves" fly-to, a units menu, and the Ignition opening sequence handing off into the live map.

**Architecture:** All new code is framework-free TypeScript under `web/src/globe/` (and `web/src/splash/`), wired through `globe.ts`. A third canvas (`flow`, 2D) sits above the overlay and draws particles and the probe marker. Pure modules (field sampling, particle stepping, readout formatting, units, peak search, fly path, intro timing) are unit-tested with Vitest; behaviour is pinned with Playwright against the reference run `2026111306`. The splash drives the globe only through an `intro` input object; Motion (motion.dev) runs the DOM timeline.

**Tech Stack:** Existing web stack (Astro 7.4.2, TypeScript 5.9.3, Vitest 4.1.12, @playwright/test 1.64.1) plus `motion@14.9.0` (exact pin; newest release at least two weeks old on 2026-11-14).

**Spec:** `docs/superpowers/specs/2026-11-14-same-sources-data-design.md` (section 10, phase 2) and `docs/superpowers/specs/2026-11-14-splash-screen-design.md`. Behaviour reference: `docs/wave-map-findings-and-plan.md` sections 5-6.

## Global Constraints

- Write all code fresh. Never copy code, CSS, text or colour values from `reference/thetidechart-capture/`. Behaviour numbers in the findings doc (particle counts, trail length, fly-to timing) are facts about behaviour and may be used as starting values.
- Never fetch from thetidechart.com.
- Byte decodings must match `pipeline/codecs.py`: height `(b/255)^2 * 16`; vector `(b-128)/127` per axis, x east, y north, pointing where waves travel, length × 25 = period s. Reuse `decodeHeight`/`decodeWave` from `web/src/globe/codecs.ts`.
- Grid comes from `globe.json`; cell (x, y) centre `lon = west + x*dlon`, `lat = north - y*dlat`; x wraps at the antimeridian.
- Canvas DPR capped at 2 (flow canvas: 1.25 on coarse-pointer devices).
- `localStorage`/`sessionStorage` reads and writes are wrapped in try/catch; the page works with storage blocked.
- Splash colours: background `#03060d`, cyan `#3fe0ff`, accent `#ff4fa3`. Wordmark text `3DWEATHER`.
- Branch `phase-2b-globe-finish`. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Existing e2e tests keep passing. They open `/wave-map?debug&nosplash#…` from Task 6 on.

Designer's calls (stated, open to correction):
- Particles: count = visible disk area / 95 px², clamped 400-5000 (max 2400 when the canvas is under 720 CSS px wide); 14-point trails stored as lon/lat; speed gain 14; speed `|v|^0.65`; east-west step divided by `cos(lat)`; respawn after a random 40-120 steps, when off the disk, past ±88°, or on land; white 1.1 px lines, alpha up to 0.55 fading with age. Under reduced motion the particles are drawn once (14 steps pre-run) and not animated.
- Probe readout lines: `2.4 m` (height), `Period 11 s`, `From NW (315°)`, coordinates `44.28° N, 140.92° W`. On land: `Land — no wave data`. Closed by Escape, by the close button, or by a drag.
- Units: length `m`/`ft`; speed `kn`/`km/h`/`m/s`/`mph`; temperature `°C`/`°F`. Defaults m, kn, °C. Stored under `localStorage["3dw.units"]` as JSON. Only length is shown in 2b; speed and temperature are stored for phase 3.
- Biggest waves: highest sea cell of the frame on screen (frame `a` of the current pair), fly 1.4 s ease-in-out (cubic), ending zoom 3.2, longitude along the shorter way round.
- Splash session flag `sessionStorage["3dw.splash"] = "1"`; `?nosplash` skips it (tests and embeds). Tagline: `Seven days of ocean, live.`

## Review Focus

1. A particle trail crossing the antimeridian or the limb → no line drawn across the screen; trail segments longer than 0.25·R CSS px are skipped.
2. A tap on land, off the disk, or at the very edge of the disk → land text or nothing; never an exception or `NaN` in the readout.
3. Storage blocked (private mode, `localStorage` throws) → units default to m/kn/°C, the menu still switches for the session, the splash still plays at most once per page load.
4. Splash with the forecast failing to load → it ends on the globe with the normal retry notice; with a deep link it ends at that place.
5. A drag that starts and ends at the same spot after moving (≥ 4 px total travel) → no probe opens; a click with < 4 px travel opens it.

Each line has its test in the owning task below.

---

### Task 1: Wave field sampling and CPU land grid

**Files:**
- Create: `web/src/globe/field.ts`, `web/src/globe/field.test.ts`
- Modify: `web/src/globe/globe.ts` (build the land grid when the mask loads; keep the current pair's pixels and mix)

**Interfaces:**
- Consumes: `decodeHeight(b)`, `decodeWave(g, b) -> { periodS, fromDeg }` from `codecs.ts`; `GlobeManifest`.
- Produces:
  - `type WaveSample = { heightM: number; periodS: number; fromDeg: number; u: number; v: number }` (`u`, `v` = decoded vector components, east/north, unitless −1…1)
  - `sampleWave(a: Uint8ClampedArray, b: Uint8ClampedArray, mix: number, m: GlobeManifest, lat: number, lon: number): WaveSample` — bilinear in space on raw bytes per channel (x wrapped, y clamped), linear in time, then decoded
  - `class LandGrid { constructor(data: Uint8ClampedArray | Uint8Array, w: number, h: number); isLand(lat: number, lon: number): boolean }` — equirectangular, lon −180 at the left pixel edge, R ≥ 128 = land
  - `landGridFrom(img: ImageBitmap, w = 512, h = 256): LandGrid` (browser only: draws into an OffscreenCanvas)

- [ ] **Step 1: Write the failing tests**

```ts
// grid 4x2, west -135, dlon 90, north 45, dlat 90 (toy manifest)
test("samples a cell centre exactly", () => {
  // cell (1,0) R=255 → 16 m
  expect(sampleWave(A, A, 0, M, 45, -45).heightM).toBeCloseTo(16);
});
test("wraps across the antimeridian", () => {
  // halfway between x=3 (lon 135) and x=0 (lon -135) → mean of their R bytes before decoding
  expect(sampleWave(A, A, 0, M, 45, 180).heightM).toBeCloseTo(decodeHeight((A_R[3] + A_R[0]) / 2));
});
test("blends in time", () => {
  expect(sampleWave(ZERO, FULL, 0.5, M, 45, -45).heightM).toBeCloseTo(decodeHeight(127.5));
});
test("vector points where waves travel", () => {
  const s = sampleWave(EAST, EAST, 0, M, 45, -45); // G=255, B=128
  expect(s.u).toBeCloseTo(1); expect(s.v).toBeCloseTo(0); expect(s.fromDeg).toBeCloseTo(270); expect(s.periodS).toBeCloseTo(25);
});
test("land grid lookup", () => {
  const g = new LandGrid(Uint8Array.from([255,0,0,0, 0,0,0,0,  0,0,0,0, 0,0,0,0]), 2, 1);
  expect(g.isLand(0, -90)).toBe(true); expect(g.isLand(0, 90)).toBe(false); expect(g.isLand(0, 180)).toBe(true); // wraps
});
```

- [ ] **Step 2: Run** `npx vitest run src/globe/field.test.ts` in `web/` — expected: FAIL, module not found.
- [ ] **Step 3: Implement** `field.ts`; in `globe.ts` keep `{ a, b, mix }` of the uploaded pair and build `landGridFrom(img)` beside `renderer.setLandMask(img)`.
- [ ] **Step 4: Run** `npm test` — expected: all passed.
- [ ] **Step 5: Commit** `feat: wave field sampling and CPU land grid`.

### Task 2: Particle trails

**Files:**
- Create: `web/src/globe/particles.ts`, `web/src/globe/particles.test.ts`
- Modify: `web/src/globe/globe.ts` (flow canvas, animation), `web/src/styles/globe.css`, `web/tests/e2e/globe.spec.ts`

**Interfaces:**
- Consumes: `sampleWave`, `LandGrid`, `project`, `radiusPx`, `View`.
- Produces:
  - `particleCount(diskAreaPx: number, cssWidth: number): number`
  - `type Field = (lat: number, lon: number) => { u: number; v: number } | null` (null = land)
  - `class Particles { constructor(rand?: () => number); resize(n: number, spawn: () => [number, number]): void; step(field: Field, spawn: () => [number, number], isGone: (lat: number, lon: number) => boolean): void; draw(ctx: CanvasRenderingContext2D, v: View, w: number, h: number): void }` — trails as `Float32Array` lon/lat rings of 14
  - `stepPoint(lat: number, lon: number, u: number, v: number): [number, number]` — `deg = 0.012 * 14 * |vec|^0.65`; `dlat = deg * v/|vec|`, `dlon = deg * u/|vec| / max(cos(lat), 0.05)`; lon wrapped
  - `segmentOk(ax: number, ay: number, bx: number, by: number, r: number): boolean` — false when the screen segment is longer than `0.25 * r`; `draw` skips such segments and points on the far side
  - `spawnOnDisk(v: View, w: number, h: number, land: LandGrid, rand: () => number): [number, number]` — random visible sea point (up to 30 tries, then any visible point)

`globe.ts`: a `canvas.globe-flow` above the overlay, same size/DPR (1.25 cap on `(pointer: coarse)`); particles step and draw every animation frame while the page is visible and not suspended; count recomputed on resize/zoom; the trail canvas is cleared each frame (no fade buffer, so trails stay glued while the globe turns). Reduced motion: pre-run 14 steps after each view or hour change, draw once.

- [ ] **Step 1: Write the failing tests**

```ts
test("count follows disk area within limits", () => {
  expect(particleCount(95 * 1000, 1200)).toBe(1000);
  expect(particleCount(10, 1200)).toBe(400);
  expect(particleCount(1e9, 1200)).toBe(5000);
  expect(particleCount(1e9, 600)).toBe(2400);
});
test("east-west steps stretch with latitude", () => {
  const [, lonEq] = stepPoint(0, 0, 1, 0), [, lon60] = stepPoint(60, 0, 1, 0);
  expect(lon60).toBeCloseTo(lonEq * 2, 5);
});
test("steps wrap longitude", () => { expect(stepPoint(0, 179.99, 1, 0)[1]).toBeLessThan(-179); });
test("particles on land respawn", () => {
  const p = new Particles(seq(0.1)); p.resize(1, () => [10, 10]);
  p.step(() => null, () => [-20, -30], () => false);
  expect(p.head(0)).toEqual([-20, -30]);
});
test("trail segments longer than 0.25 R are not drawn", () => {
  expect(segmentOk(0, 0, 10, 0, 100)).toBe(true);
  expect(segmentOk(0, 0, 26, 0, 100)).toBe(false); // e.g. a wrap across the limb
});
```

(`head(i): [lat, lon]` is a small accessor added for tests and the probe-free debug view.)

Add to the smoke test: at `#20,-30,1` the flow canvas has at least 200 pixels with alpha > 0 after ready; no console errors.

- [ ] **Step 2: Run** `npm test` — expected: FAIL.
- [ ] **Step 3: Implement** `particles.ts` and the flow canvas wiring.
- [ ] **Step 4: Run** `npm test && npx playwright test` — expected: all passed. Screenshot `#20,-30,1` into the workspace and check the trails follow the swell (they should stream eastwards across the North Atlantic storm at hour 90).
- [ ] **Step 5: Commit** `feat: wave particle trails`.

### Task 3: Units

**Files:**
- Create: `web/src/globe/units.ts`, `web/src/globe/units.test.ts`
- Modify: `web/src/pages/wave-map.astro` (header with the settings button), `web/src/globe/globe.ts`, `web/src/styles/globe.css`

**Interfaces:**
- Produces:
  - `type Units = { length: "m" | "ft"; speed: "kn" | "kmh" | "ms" | "mph"; temp: "C" | "F" }`; `DEFAULT_UNITS = { length: "m", speed: "kn", temp: "C" }`
  - `formatLength(m: number, u: Units["length"]): string` — `"2.4 m"` / `"7.9 ft"`, one decimal
  - `formatSpeed(ms: number, u: Units["speed"]): string` — whole numbers: `"19 kn"`, `"36 km/h"`, `"10 m/s"`, `"22 mph"`
  - `formatTemp(c: number, u: Units["temp"]): string` — `"18 °C"` / `"64 °F"`
  - `loadUnits(store?: Storage | null): Units` (invalid or missing fields → defaults; throwing storage → defaults); `saveUnits(u: Units, store?: Storage | null): void` (swallows errors)
  - `mountUnitsMenu(button: HTMLButtonElement, onChange: (u: Units) => void): Units` — a popover with three radio groups; Escape and outside click close it; returns the loaded units

- [ ] **Step 1: Write the failing tests**

```ts
test("lengths", () => { expect(formatLength(2.44, "m")).toBe("2.4 m"); expect(formatLength(2.44, "ft")).toBe("8.0 ft"); });
test("speeds", () => { expect(formatSpeed(10, "kn")).toBe("19 kn"); expect(formatSpeed(10, "kmh")).toBe("36 km/h"); expect(formatSpeed(10, "mph")).toBe("22 mph"); });
test("temperatures", () => { expect(formatTemp(18, "F")).toBe("64 °F"); });
test("storage that throws gives defaults", () => {
  const bad = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } } as unknown as Storage;
  expect(loadUnits(bad)).toEqual(DEFAULT_UNITS); expect(() => saveUnits(DEFAULT_UNITS, bad)).not.toThrow();
});
test("bad stored values fall back per field", () => {
  const s = fakeStorage({ "3dw.units": JSON.stringify({ length: "ft", speed: "warp" }) });
  expect(loadUnits(s)).toEqual({ length: "ft", speed: "kn", temp: "C" });
});
```

- [ ] **Step 2: Run** `npm test` — expected: FAIL.
- [ ] **Step 3: Implement** `units.ts`, the header button (`aria-haspopup="dialog"`, label "Units") and the menu; `globe.ts` keeps the current `Units` and passes length to the legend tick labels (ft ticks show `3, 10, 20, 30, 40` placed at their metre positions).
- [ ] **Step 4: Run** `npm test && npx playwright test` — expected: all passed.
- [ ] **Step 5: Commit** `feat: units menu stored per browser`.

### Task 4: Tap readout (probe)

**Files:**
- Create: `web/src/globe/probe.ts`, `web/src/globe/probe.test.ts`
- Modify: `web/src/globe/gestures.ts` (report clicks), `web/src/globe/globe.ts`, `web/src/styles/globe.css`, `web/tests/e2e/globe.spec.ts`

**Interfaces:**
- Consumes: `sampleWave`, `LandGrid.isLand`, `unproject`, `formatLength`, `Units`.
- Produces:
  - `compass(deg: number): string` — 8 points: `N NE E SE S SW W NW`
  - `formatCoord(lat: number, lon: number): string` — `"44.28° N, 140.92° W"`
  - `readoutLines(s: WaveSample | null, lat: number, lon: number, u: Units): string[]` — sea: `[length, "Period 11 s", "From NW (315°)", coord]`; land (`null`): `["Land — no wave data", coord]`; heights under 0.05 m read `"Calm"` in place of the length
  - `attachGestures(..., onTap?: (x: number, y: number) => void)` — new optional last parameter; fires on pointerup when total travel since pointerdown < 4 CSS px and only one pointer was down
  - `class Probe { constructor(root: HTMLElement); show(lat: number, lon: number, lines: string[]): void; hide(): void; at(): { lat: number; lon: number } | null }` — panel `role="dialog"` `aria-label="Conditions here"` with a close button; marker drawn by `globe.ts` on the flow canvas (ring, 6 px, cyan)

`globe.ts`: tap → `unproject`; off-disk → hide; else show with `readoutLines`. The readout refreshes when the hour or units change; a drag hides it; Escape hides it.

- [ ] **Step 1: Write the failing tests**

```ts
test("compass", () => { expect(compass(315)).toBe("NW"); expect(compass(359)).toBe("N"); expect(compass(22.4)).toBe("N"); expect(compass(22.6)).toBe("NE"); });
test("coords", () => { expect(formatCoord(44.28, -140.92)).toBe("44.28° N, 140.92° W"); expect(formatCoord(-33.9, 18.4)).toBe("33.90° S, 18.40° E"); });
test("sea readout", () => {
  expect(readoutLines({ heightM: 2.44, periodS: 11.2, fromDeg: 315, u: 0, v: 0 }, 44.28, -140.92, DEFAULT_UNITS))
    .toEqual(["2.4 m", "Period 11 s", "From NW (315°)", "44.28° N, 140.92° W"]);
});
test("land readout", () => { expect(readoutLines(null, 40.4, -3.7, DEFAULT_UNITS)[0]).toBe("Land — no wave data"); });
test("no NaN at the limb", () => { expect(readoutLines(null, 90, 180, DEFAULT_UNITS).join(" ")).not.toMatch(/NaN/); });
```

Add to the smoke test: a click at the centre of `#44.28,-140.92,4` opens the dialog containing `/1[34]\.\d m/`; switching units to ft changes it to `/4[3-6]\.\d ft/`; a click at `#40.4,-3.7,4` shows "Land"; a 200 px drag does not open the dialog; a drag 30 px out and back to the start point does not open it either (Review Focus 5); Escape closes it.

- [ ] **Step 2: Run** `npm test` — expected: FAIL.
- [ ] **Step 3: Implement** `probe.ts`, the tap callback and the wiring.
- [ ] **Step 4: Run** `npm test && npx playwright test` — expected: all passed.
- [ ] **Step 5: Commit** `feat: tap readout for wave conditions`.

### Task 5: Biggest waves

**Files:**
- Create: `web/src/globe/fly.ts`, `web/src/globe/fly.test.ts`
- Modify: `web/src/globe/globe.ts`, `web/src/pages/wave-map.astro` (button in the controls bar), `web/src/styles/globe.css`, `web/tests/e2e/globe.spec.ts`

**Interfaces:**
- Consumes: `decodeHeight`, `LandGrid`, `GlobeManifest`, `View`, `clampView`, `wrapLon`, `Probe`.
- Produces:
  - `biggestWave(pixels: Uint8ClampedArray, m: GlobeManifest, land: LandGrid): { lat: number; lon: number; heightM: number }` — highest R byte over cells whose centre is sea; ties → first in row order
  - `easeInOutCubic(t: number): number`
  - `flyView(from: View, to: View, t: number): View` — eased; longitude by the shorter way; zoom interpolated geometrically
  - `FLY_MS = 1400`, `FLY_ZOOM = 3.2`

`globe.ts`: the "Biggest waves" button runs the search on frame `a`, flies there, then opens the probe at that point. Any pointer down on the globe cancels the flight.

- [ ] **Step 1: Write the failing tests**

```ts
test("finds the highest sea cell", () => { /* toy frame with a 250 byte on land and 240 at sea */ expect(biggestWave(px, M, land)).toEqual({ lat: 45, lon: 45, heightM: decodeHeight(240) }); });
test("flies the short way round", () => {
  const mid = flyView({ lat0: 0, lon0: 170, zoom: 1 }, { lat0: 0, lon0: -170, zoom: 1 }, 0.5);
  expect(Math.abs(Math.abs(mid.lon0) - 180)).toBeLessThan(1e-6);
});
test("ends exactly on target", () => { expect(flyView(A, B, 1)).toEqual(clampView(B)); });
test("ease", () => { expect(easeInOutCubic(0)).toBe(0); expect(easeInOutCubic(0.5)).toBe(0.5); expect(easeInOutCubic(1)).toBe(1); });
```

Add to the smoke test: at hour 0, clicking "Biggest waves" ends (within 2.5 s) with `__globe.view()` within 1° of `44.28, -140.92` and zoom 3.2, and the probe shows `/1[34]\.\d m/` — the reference run's published peak.

- [ ] **Step 2: Run** `npm test` — expected: FAIL.
- [ ] **Step 3: Implement** `fly.ts` and the button.
- [ ] **Step 4: Run** `npm test && npx playwright test` — expected: all passed.
- [ ] **Step 5: Commit** `feat: biggest waves fly-to`.

### Task 6: Ignition splash

**Files:**
- Create: `web/src/splash/intro.ts`, `web/src/splash/intro.test.ts`, `web/src/splash/splash.ts`, `web/src/styles/splash.css`
- Modify: `web/package.json` (`motion` 14.9.0 exact), `web/src/globe/globe.ts`, `web/src/globe/renderer.ts` (body alpha uniform), `web/src/globe/overlay.ts` (coast reveal fraction), `web/src/globe/particles.ts` (arrival), `web/src/pages/wave-map.astro`, `web/tests/e2e/globe.spec.ts`, `web/tests/e2e/splash.spec.ts`

**Interfaces:**
- Consumes: `GlobeHandle`, `Latest`, `Particles`, `drawOverlay`, `GlobeRenderer`.
- Produces:
  - `type Intro = { arrival: number; body: number; coast: number; zoom: number }` — each 0…1 except `zoom`, a multiplier on the view zoom
  - `INTRO_S = 3.0`; `introAt(t: number): Intro` — piecewise from the spec table: `arrival` 0→1 over 0.55-1.3 s; `body` 0→1 over 0.9-1.4 s; `coast` 0→1 over 1.35-1.95 s; `zoom` 0.82 until 2.45 s then eased to 1.0 at 3.0 s; all clamped; `introAt(≥3)` = `{1,1,1,1}`
  - `shouldPlay(search: string, store: Storage | null): boolean` — false with `nosplash` in the query or the session flag set; storage errors → true
  - `markPlayed(store: Storage | null): void` (swallows errors)
  - `scramble(target: string, progress: number, rand: () => number): string` — characters resolve left to right; at 1 equals target
  - `GlobeHandle.setIntro(i: Intro | null): void` — renderer multiplies the globe body and limb by `body`; overlay draws the first `coast` fraction of each line's points; particles lerp from an edge start point to their position by `arrival`; view zoom × `zoom`
  - `playSplash(root: HTMLElement, globe: GlobeHandle, latest: Latest | null, opts: { reduced: boolean; dataReady: Promise<void> }): Promise<void>` — Motion drives one progress value 0→3 s with `animate(0, 3, { duration: 3, ease: "linear", onUpdate })` and the DOM parts (horizon line, readouts, wordmark, tagline) with `animate` sequences; any pointerdown, keydown or wheel ends it at once; if data is not ready at 2.45 s it holds there with particles drifting until `dataReady` resolves (or rejects: then finishes and the globe's retry notice shows); the splash layer is `aria-hidden="true"` and removed at the end. Reduced motion: 300 ms fade only, no particle arrival.

Readouts: `RUN 2026-11-13 06Z`, `MODEL GFS-WAVE · OPEN-METEO`, `CELLS` counting up to `294,912` (768 × 384) — from `latest.json` and the manifest, never fixed text. `globe.ts` exposes `latest` on the handle (`run(): string | null`).

- [ ] **Step 1: Write the failing tests**

```ts
test("intro timing", () => {
  expect(introAt(0)).toEqual({ arrival: 0, body: 0, coast: 0, zoom: 0.82 });
  expect(introAt(1.35).coast).toBe(0);
  expect(introAt(1.95).coast).toBeCloseTo(1);
  expect(introAt(2.45).zoom).toBeCloseTo(0.82);
  expect(introAt(3)).toEqual({ arrival: 1, body: 1, coast: 1, zoom: 1 });
  expect(introAt(99)).toEqual({ arrival: 1, body: 1, coast: 1, zoom: 1 });
});
test("plays once per session, never with nosplash", () => {
  const s = fakeStorage({});
  expect(shouldPlay("", s)).toBe(true); markPlayed(s); expect(shouldPlay("", s)).toBe(false);
  expect(shouldPlay("?nosplash", fakeStorage({}))).toBe(false);
  expect(shouldPlay("", throwingStorage)).toBe(true);
});
test("scramble resolves left to right", () => {
  expect(scramble("ABC", 1, Math.random)).toBe("ABC");
  expect(scramble("ABC", 1 / 3, () => 0)[0]).toBe("A");
});
```

`splash.spec.ts` (with `test.use({ reducedMotion: "no-preference" })`):
- first visit shows `.splash`; it is gone within 4.5 s and `__globe.ready` is true;
- a reload in the same page context shows no `.splash`;
- pressing a key at 0.5 s removes `.splash` within 300 ms;
- opening `#40.4,-3.7,4` ends with `__globe.view()` equal to that place, zoom 4;
- with every `globe-w*.webp` aborted the splash still ends within 5 s and the retry notice is visible.
And one with `reducedMotion: "reduce"`: `.splash` is gone within 800 ms.

Change the existing smoke tests' `open()` and direct `goto`s to `/wave-map?debug&nosplash…`.

- [ ] **Step 2: Run** `npm test` — expected: FAIL.
- [ ] **Step 3: Install** `npm install --save-exact motion@14.9.0` in `web/`. Check the Motion 14 vanilla `animate` API against its docs (https://motion.dev/docs/animate) before writing `splash.ts`.
- [ ] **Step 4: Implement** `intro.ts`, `splash.ts`, `splash.css`, the intro inputs in renderer/overlay/particles and the page wiring.
- [ ] **Step 5: Run** the whole suite: `npm test && npx playwright test` in `web/`, and `.venv/Scripts/python -m pytest -q -m "not reference"` at the root — expected: all passed.
- [ ] **Step 6: Look at it.** Capture frames at 0.3, 0.9, 1.5, 2.0, 2.6 and 3.2 s into the workspace and compare against the spec table and `docs/design/splash-concepts.html` (Ignition).
- [ ] **Step 7: Commit** `feat: Ignition splash into the live globe`.
