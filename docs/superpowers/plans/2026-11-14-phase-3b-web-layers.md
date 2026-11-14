# Phase 3b: every globe layer on the web — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Five globe pages (rain, wind, temperature, waves, currents) built from the phase 3a sprites. Each page has its own URL, colour scale, legend, particles, readout and "biggest" button, and you can switch between them without reloading.

**Architecture:** A layer registry (`layers.ts`) describes each layer: the sprite families it loads, how the shader turns bytes into colour, its ramp and legend, its particle vectors, its readout lines and its peak series. The globe takes a layer id and can switch layers in place. One Astro component renders all five pages; each page file only names its layer.

**Tech Stack:** Astro 7.4.2, TypeScript 5.9.3, WebGL1, Vitest 4.1.12, Playwright 1.64.1.

**Spec:** `docs/superpowers/specs/2026-11-14-same-sources-data-design.md`, with the behaviour list in `docs/wave-map-findings-and-plan.md` §6 (layer switch, readout, biggest, units). Byte decodes are in findings §4 and must match `pipeline/codecs.py`.

## Global Constraints

- URLs as on the reference site: `/weather-map` (rain and cloud), `/wind-map`, `/temperature-map`, `/wave-map`, `/ocean-currents-map`. Switching uses `history.replaceState` plus a title swap and keeps the `#lat,lon,zoom` hash and the forecast hour. Without JavaScript the tabs are plain links.
- Families per layer: rain `a`+`b` (cloud veil from `b.R`) · wind `a` (+`b` for gusts in the readout) · temperature `t` (+`a` for wind particles) · waves `w` · currents `c` (single file, 8 daily frames, `currentEvery` 24).
- Colour ramps are our own; never copy the reference's colours.
- Sea-only layers (waves, currents) keep land in the land colour. Rain, wind and temperature draw over land.
- Credits per layer name each source and its licence (Open-Meteo CC BY 4.0; NOAA GFS / GFS-Wave; ECMWF IFS CC BY 4.0; "E.U. Copernicus Marine Service Information").
- Units: speed (kn, km/h, m/s, mph) and temperature (°C, °F) from the existing menu. Rain is shown in mm/h, or in/h when length is ft. Currents use the speed unit.
- Pin exact versions; no new dependencies.

## Review Focus

1. **Switching layers mid-load** — a slow chunk from the old layer must never paint over the new layer. Test in Task 4.
2. **Gusts past 84 h** — the wind readout omits gusts rather than showing 0. Test in Task 3.
3. **Currents at hour 167 → 168** — the daily frame pair clamps at frame 7; no fetch of a ninth frame. Test in Task 2.
4. **Calm wind or zero current** — particles stay put without NaN, and the readout says "Calm" or "Slack". Test in Task 3.
5. **The deep link and hour survive a switch** — the hash and timeline position are unchanged after clicking a tab. Test in Task 5.

---

### Task 1: Byte decodes and layer registry

**Files:**
- Modify: `web/src/globe/codecs.ts`, `web/src/globe/ramp.ts`
- Create: `web/src/globe/layers.ts`
- Test: `web/src/globe/codecs.test.ts`, `web/src/globe/layers.test.ts`

**Interfaces:**
- Produces:
  - `decodeWind(b)`, `decodeGust(b)`, `decodeRain(b)`, `decodeAirTemp(b)`, `decodeSeaTemp(b)`, `decodeCurrent(b)`, `decodePressure(b) -> number | null` (0 → null), `decodeCloud(b)`, with the same formulas as `pipeline/codecs.py`.
  - `type LayerId = "rain" | "wind" | "temperature" | "waves" | "currents"`.
  - `type Layer = { id, path, title, heading, description, families: Family[], shade: Shade, ramp: [number, Rgba][], legend: LegendSpec, overLand: boolean, flow: FlowSpec, peak: string, biggestLabel: string, credits: string, model: string }`.
    - `Shade` is `{ family, kind: "scalar", channel }` or `{ family, kind: "vector", channels: [r, g] }`.
    - `FlowSpec` is `{ family, channels: [u, v], scale, seaOnly }`.
  - `LAYERS: Record<LayerId, Layer>` and `layerForPath(path) -> LayerId`.
  - `rampTable(layer) -> Uint8Array` (256 RGBA). The index is the byte for scalar layers; for vector layers it is speed scaled 0..255 over the layer's max (wind 0–40 m/s, currents 0–2 m/s, square-root spaced).

- [ ] **Step 1: Write the failing tests:** each decode against the Python formula at bytes 0, 1, 128, 255; `decodePressure(0) === null`; `layerForPath("/wind-map") === "wind"` and unknown → `"waves"`; every layer's ramp is monotone in its value axis and has ≥ 5 stops; `rampTable(LAYERS.wind)[0..3]` is the calm colour.
- [ ] **Step 2: Run, expect FAIL:** `cd web && npx vitest run src/globe/codecs.test.ts src/globe/layers.test.ts`.
- [ ] **Step 3: Implement.** Keep the wave ramp as it is; add our own ramps for rain (transparent → blue → violet), wind (navy → teal → yellow → magenta), temperature (violet −40 °C → blue → green 15 → orange → dark red 45 °C) and currents (dark → cyan → white).
- [ ] **Step 4: Run** → pass, then `npx vitest run`.
- [ ] **Step 5: Commit** `feat: byte decodes and layer registry for every globe layer`.

### Task 2: Frame stores for several families and the daily ocean file

**Files:**
- Modify: `web/src/globe/frames.ts`, `web/src/globe/manifest.ts`
- Test: `web/src/globe/frames.test.ts`, `web/src/globe/manifest.test.ts`

**Interfaces:**
- Produces:
  - `GlobeManifest` gains optional `currentEvery?`, `currentFrames?`, `gustHours?` and the other flags.
  - `type Sheet = { family: Family; chunks: number[]; every: number; url(chunk): string }`, plus `sheetFor(m, family) -> Sheet`. `c` → one chunk of `currentFrames`, `every = currentEvery`, url `globe-c.webp`. Others → `m.chunks`, `m.every`, `globe-{f}{i}.webp`.
  - `framePairFor(sheet, hours, hour)` generalises `framePair` (clamps at the last frame).
  - `FrameStore(base, dir, sheet, opts)` (the old `family` and manifest params become a sheet).
  - `LayerFrames`: one `FrameStore` per family of a layer. `ensure(hour) -> Promise<Record<Family, {a, b, mix}> | null>`.

- [ ] **Step 1: Write the failing tests:** `sheetFor(m, "c")` gives chunks `[8]`, every 24; `framePairFor(c, 168, 167.5)` → `{a: 6, b: 7}` and at 168 → `{a: 7, b: 7, mix: 0}`; a `LayerFrames` for rain loads `globe-a0` and `globe-b0` and nothing else; an existing retry test still passes with the new constructor.
- [ ] **Step 2: Run, expect FAIL:** `npx vitest run src/globe/frames.test.ts src/globe/manifest.test.ts`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → pass; whole unit suite.
- [ ] **Step 5: Commit** `feat: frame stores for several sprite families and the daily ocean file`.

### Task 3: Samples, readout and particle vectors per layer

**Files:**
- Modify: `web/src/globe/field.ts`, `web/src/globe/probe.ts`, `web/src/globe/units.ts`
- Test: `web/src/globe/field.test.ts`, `web/src/globe/probe.test.ts`, `web/src/globe/units.test.ts`

**Interfaces:**
- Produces:
  - `sampleBytes(px, m, lat, lon, channels)` (bilinear on raw bytes) and `sampleLayer(layer, frames, m, lat, lon, hour) -> Sample`. A sample is `{ windMs?, windFromDeg?, gustMs?, rainMmh?, cloudPct?, airC?, waveM?, periodS?, waveFromDeg?, currentMs?, currentToDeg?, seaC? }`, holding only what the layer's families provide. Gust is omitted past `gustHours`.
  - `flowVector(layer, frames, m, lat, lon) -> {u, v} | null`: normalised by `flow.scale` (wind 25 m/s, currents 1 m/s, waves unchanged). Null on land when `flow.seaOnly`.
  - `formatRain(mmh, length)`: "1.2 mm/h", or "0.05 in/h" for ft.
  - `readoutFor(layer, sample, lat, lon, units) -> string[]`:
    - wind: "Wind 12 kn from SW (225°)", "Gusts 18 kn" (only when present), or "Calm" below 0.5 m/s;
    - rain: "Rain 1.2 mm/h" or "No rain" below 0.05, then "Cloud 60 %";
    - temperature: "Air 15 °C";
    - waves: unchanged lines;
    - currents: "Current 0.8 kn toward E" or "Slack" below 0.05 m/s, then "Sea 18 °C";
    - each ends with the coordinate. Sea-only layers on land read "Land — no wave data" or "Land — no current data".

- [ ] **Step 1: Write the failing tests:** one readout test per layer with fixed samples, including calm, slack, no rain, gust omitted, and °F/mph/in/h variants; `flowVector` for currents on land → null; wind with u = v = 0 → `{u: 0, v: 0}` (no NaN).
- [ ] **Step 2: Run, expect FAIL:** `npx vitest run src/globe/field.test.ts src/globe/probe.test.ts src/globe/units.test.ts`.
- [ ] **Step 3: Implement.** Keep `sampleWave` and `readoutLines` as thin wrappers so existing tests stay valid.
- [ ] **Step 4: Run** → pass; whole unit suite.
- [ ] **Step 5: Commit** `feat: readouts and particle vectors for every layer`.

### Task 4: Renderer and globe driven by the layer

**Files:**
- Modify: `web/src/globe/renderer.ts`, `web/src/globe/globe.ts`, `web/src/globe/ui.ts`, `web/src/globe/fly.ts`
- Test: `web/src/globe/fly.test.ts`; e2e in Task 5

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `GlobeRenderer.setLayer(layer)` uploads the layer's ramp and sets the uniforms `uKind` (0 scalar, 1 vector), `uChannel`, `uVecMax`, `uOverLand`, `uVeil` (rain: cloud from the second family). `setFrames(primary, secondary?)` binds up to two frame pairs (units 0/1 and 4/5).
  - `initGlobe(root, {layer, …})`, and the handle gains `layer(): LayerId` and `setLayer(id): Promise<void>`. A switch bumps a load sequence number, so frames from the old layer are dropped when they arrive.
  - `mountLegend(root, layer, units)` rebuilds for the layer.
  - `peakAt(m, key, hour) -> {lat, lon} | null` from manifest peaks. Biggest waves keeps its frame scan; other layers fly to the manifest peak.
  - `info()` also returns the layer's model label for the splash.

- [ ] **Step 1: Write the failing test:** `peakAt` returns the entry for `Math.round(hour)`, clamped to the series length (gust series 85).
- [ ] **Step 2: Run, expect FAIL:** `npx vitest run src/globe/fly.test.ts`.
- [ ] **Step 3: Implement** renderer and globe changes. The shader keeps one program, with branches on `uKind` and `uOverLand`. Over land with `uOverLand`, it blends 25 % land colour into the layer colour so coasts stay readable.
- [ ] **Step 4: Run** unit suite → pass; `npm run build` → no type errors.
- [ ] **Step 5: Commit** `feat: the globe renders any layer and switches in place`.

### Task 5: Five pages, the layer switch, end-to-end tests

**Files:**
- Create: `web/src/components/GlobePage.astro`, `web/src/pages/weather-map.astro`, `web/src/pages/wind-map.astro`, `web/src/pages/temperature-map.astro`, `web/src/pages/ocean-currents-map.astro`
- Modify: `web/src/pages/wave-map.astro` (uses the component), `web/src/styles/globe.css` (tabs)
- Test: `web/tests/e2e/layers.spec.ts`; `globe.spec.ts` and `splash.spec.ts` stay green

**Interfaces:**
- Consumes: Task 4.
- Produces:
  - A `GlobePage` prop `layer: LayerId`; the header nav is a `nav[aria-label="Map layers"]` of five links, with `aria-current="page"` on the active one.
  - JavaScript intercepts clicks on the links: `setLayer`, `history.replaceState` to the new path with the same hash, a title swap, and the active tab and credits updated.

- [ ] **Step 1: Write the failing e2e tests** (`?debug&nosplash`):
  - each of the five URLs loads, shows its legend title, and paints a non-sea colour somewhere (wind and temperature everywhere; rain over the ITCZ near 0°, −120° at hour 0; currents near the Agulhas peak at −39.6, 21.27);
  - a tab switch keeps the hash and hour, updates the URL, the title and `aria-current`, and has no console errors;
  - wind readout at the reference wind peak (44.75, −140.45) reads ≥ 50 kn;
  - the currents readout at the Agulhas peak reads a current and a sea temperature;
  - "Strongest wind" flies to the manifest wind peak;
  - a slow `globe-w*` route on the wave page followed by an immediate switch to wind leaves the wind colours on screen.
- [ ] **Step 2: Run, expect FAIL:** `npx playwright test tests/e2e/layers.spec.ts`.
- [ ] **Step 3: Implement** the component, pages and switch.
- [ ] **Step 4: Run** all e2e: `npx playwright test` → all pass; unit suite → pass.
- [ ] **Step 5: Commit** `feat: rain, wind, temperature and currents pages with an in-place layer switch`.
