# Phase 6: Regional Maps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flat, hourly, 72-hour wind / rain / cloud maps for 12 regions at `/weather-map/{region}` (and `/wind-map/{region}`), built by the same 6-hourly run.

**Architecture:** The run builds, next to the globe, one 2× finer grid per region (every second GFS 13 km node), hourly 0–72 h: `{region}-a.webp` (u, v, rain) and `{region}-b.webp` (cloud) in 8 columns, plus `{region}.json` (grid, focus, time zone, cities, hourly wind and rain peaks). Static land outlines per region come from Natural Earth. The browser draws the map on four stacked 2D canvases (base, field, flow, top), equirectangular with x scaled by cos(focus latitude).

**Tech Stack:** Python 3 (numpy, omfiles, Pillow, pytest); Astro 7, TypeScript, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-14-same-sources-data-design.md` (§5 steps 2, 4, 5; §10 phase 6; §11 regional bounds left to the builder). Format notes: `docs/wave-map-findings-and-plan.md` §10 ("Flat regional map files").

## Global Constraints

- Regional grid: every second node of the GFS 13 km grid (`ncep_gfs013`, dlon 360/3072, dlat 179.82425/1535), so dlon = 0.234375°; hourly, 72 h, 73 frames; sprites in 8 columns.
- Encodings are the globe's: wind byte 128 = calm, ±127 = ±50 m/s; rain (byte/255)² × 64 mm/h; cloud byte / 2.55 %.
- The 12 region slugs: `united-states`, `united-kingdom`, `scotland`, `ireland`, `europe`, `india`, `west-pacific`, `philippines`, `australia`, `new-zealand`, `canada`, `south-africa`.
- Europe's grid must equal the captured reference manifest: w 350, h 167, north 71.9882746742671, south 33.09469096091206, west −39.9609375, east 41.8359375.
- Model credit on every regional page: "NOAA GFS via Open-Meteo.com (CC BY 4.0)"; coastlines Natural Earth.
- Never commit `reference/`; never fetch from thetidechart.com; write code fresh; Python file I/O with `encoding="utf-8"`.

## Review Focus

1. **Regions near the antimeridian or poles** (New Zealand to 179.5° E, West Pacific): node indices wrap in longitude; no region crosses ±180.
2. **The first and last hours**: GFS has no rain or cloud at hour 0; hour 72 rain reads precipitation at hour 73. Neither may crash or show NaN.
3. **Eviction with `--prune`**: a regional hour must never ask for a GFS file the globe loop already deleted.
4. **Time zones in the peaks text**: region-local times, including half-hour zones (India).
5. **Narrow phones**: the map, controls and region list fit 320 px with no horizontal page scroll.

---

### Task 1: Region catalogue and regional grid

**Files:** Create `pipeline/regions.py`, `tests/test_regions.py`.

**Interfaces — Produces:**
- `Region(slug, title, west, east, south, north, focus: tuple[float,float,float,float], tz, place, cities: list[tuple[str,float,float]])`; `REGIONS: list[Region]` (12, order above).
- `RegionGrid.of(region, sg: SourceGrid) -> RegionGrid` with `w, h, north, south, west, east, i0, j0` (source node of the north-west cell), `lats()`, `lons()`, `manifest_fields()`.
- `sample(field: np.ndarray, sg: SourceGrid, rg: RegionGrid) -> np.ndarray` (h × w, north first): the rule chosen in Task 2 against the reference peaks (point / tent / box), NaN-aware, x wrapped.
- `region_peak(field, rg) -> [value 1dp, lat 2dp, lon 2dp]`.

Tests: Europe grid equals the reference values (Global Constraints); every region has ≥ 6 cities inside its bounds, a valid IANA zone, and its focus box inside its grid; constant field samples exactly; a one-node spike lands on the right cell; a region whose nodes run past index 3071 wraps.

### Task 2: Regional frames in the run

**Files:** Modify `pipeline/build.py`, `pipeline/sprites.py` (`pack_frames(frames, cols, h, w)`), `pipeline/atmosphere.py` (rain over any target grid); test `tests/test_build.py`, `tests/test_reference_run.py`.

- Hourly regional hours 0..72 are made inside the globe loop: at globe frame time t, the regional hours in (t−3 h, t] (hour 0 at frame 0). GFS eviction keeps from t_next − 2 h.
- `_check_complete` also needs GFS u, v, cloud layers at hours 0..72 and precipitation at 1..73.
- Each hour per region: u, v, cloud (our cloud rule), rain = mean over (t−1 h, t+1 h] like the globe (no extra smoothing), all with `sample`.
- Writes `{slug}-a.webp` (R u, G v, B rain) and `{slug}-b.webp` (R G B = cloud) of 73 frames, 8 columns; `{slug}.json` = `{region, run, hours: 72, cols: 8, w, h, north, south, west, east, focus, tz, place, cities, peaks: {wind, rain}, masked: false}`; `latest.json` gains `"regions": [slugs]`.
- Tests (fakes): sizes (8·w × 10·h), manifest keys, hour 0 rain/cloud empty, prune never evicts a regional hour still needed. Reference test: Europe wind and rain peaks every hour 0..72 within 2 regional cells and 1.0 m/s / 1.0 mm/h (rain: hours where both are ≥ 1 mm/h). Pick the sampling rule that passes; ledger it.

### Task 3: Regional land outlines

**Files:** Modify `pipeline/static_assets.py`; test `tests/test_static_assets.py`.

- `clip_ring(ring, bbox)` (Sutherland–Hodgman) and `region_land(geojson, region) -> {"region", "west", "east", "south", "north", "rings": [[lon, lat, …], …]}` with rings clipped to the grid bounds plus one cell, rounded to 3 dp, rings under 3 points dropped.
- `build_static` writes `regions/{slug}.json` beside the globe assets (same upload, prefix `assets/globe`).
- Tests: square clipped to a half-square; ring outside dropped; every region file has at least one ring (Natural Earth fixture).

### Task 4: Flat regional map in the browser

**Files:** Create `web/src/region/` (`flat.ts` projection and view, `frames.ts` sprite loading, `field.ts` sampling + readout, `map.ts` canvases, particles, probe, timeline, legend), `web/src/components/RegionPage.astro`, `web/src/pages/weather-map/[region].astro`, `web/src/pages/wind-map/[region].astro`; unit tests beside each module.

- View `{lon0, lat0, zoom}`; px per degree = zoom · fit, x scaled by cos(focus latitude); initial view fits the focus box; pan and wheel/pinch zoom clamped to the grid.
- Two layers: "Rain + clouds" (cloud white veil, rain coloured with the globe's rain ramp) and "Wind" (globe wind ramp, particles). Legend, units menu, timeline (72 h, region time zone), tap readout (wind speed and direction, gust-free; rain mm/h; cloud %).
- Page text: region title and description, region list (12 + "Whole world" → `/weather-map`), credits, "The next three days in {region}" with strongest wind and heaviest rain from `peaks` in region-local time.
- Unit tests: projection round trip; frame extraction from an 8-column sheet; readout strings; peaks summary in a half-hour zone.

### Task 5: End-to-end and docs

**Files:** `web/tests/e2e/region.spec.ts`; `docs/deploy.md`; README.

- `/weather-map/europe` loads, legend "Rain", field painted over the Bay of Biscay; switching to Wind changes the colour; timeline hour 0 → 24 changes the field; tap readout has wind and rain; `/wind-map/europe` opens on Wind; every region page returns 200 and lists 12 regions; no horizontal scroll at 320 px.
