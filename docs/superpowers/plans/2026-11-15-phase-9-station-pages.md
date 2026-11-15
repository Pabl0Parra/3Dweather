# Phase 9: Station Pages, Station Weather and the Daily Page Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every station page shows its tides (today's chart, the 30-day table, other months, CSV), sun and moon, solunar periods and coefficient, and the weather and sea forecast for the next 7 days; a daily workflow rebuilds and publishes the pages.

**Architecture:** The forecast run samples every station into one file per region (`wx/{run}/stations/{cc}/{region}.json`, spec §5 step 6, carried over from phase 8). A daily Python step (`pipeline/station_pages.py`) writes one data file per station (the calendar month of tides and sky, three days of 10-minute curve), which the Astro page embeds as JSON and prints as HTML. Framework-free TypeScript (`web/src/station/`) draws the chart, marks "now", and fills in the weather, other months and CSV in the browser.

**Tech Stack:** Python (numpy, skyfield via `[sky]`, h5py not needed), Astro 7 + TypeScript, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-14-same-sources-data-design.md` §5 step 6, §6 ("Tides" outputs, "Weather and sea", "Serving"), §7 (Station pages daily), §10 step 9.

## Global Constraints

- Times in files are UTC or local "HH:MM" with minutes since local midnight (phase 8 convention); pages show the station's local time and say which zone.
- Heights in metres above mean sea level; pages print two decimals and a unit switch (m / ft) remembered per viewer.
- The pages say tides are predictions, astronomical only, "not NOAA's official predictions", and name the source (NOAA station, offsets on a reference, the donor station, or EOT20/FES2022).
- Weather is filled in by the browser from the newest run; pages work (tides and sky) with no weather file.
- Python file I/O passes `encoding="utf-8"`. No reference values copied into the repository.

## Review Focus

1. **A station without tides** (`kind: none`): the page says so plainly; no empty chart, no NaN.
2. **The visitor's date is not the build date** (page built yesterday, or the visitor is in another zone): "today" is the station's local today, taken from the embedded month, and the chart still draws.
3. **DST change days** (23 h / 25 h): the chart's time axis and table times are right.
4. **No weather file yet or a station missing from it**: the weather section says "not available", nothing breaks.
5. **Month end**: "next 7 days" and the 30-day table cross into the next month without gaps (the tide-table file covers it).

---

### Task 1: Station weather in every forecast run

**Files:** Create `pipeline/station_wx.py`, `tests/test_station_wx.py`; modify `pipeline/build.py`, `pipeline/__main__.py`/`cycle.py` (catalogue path), `.github/workflows/forecast.yml` (download `catalogue/stations.json`, optional).

**Interfaces — Produces:** `StationSampler(records)`; `.add(t: datetime, name: str, field: np.ndarray, grid, sea: bool = False)` (grid is a `SourceGrid` or `GLOBE`; `sea` takes the nearest finite cell within 3 cells); `.write(run_dir: Path) -> int` writing `stations/{cc}/{region}.json` = `{"v":1, "run", "start", "step_h": 3, "fields": [...], "scale": {...}, "stations": {id: {field: [int | null, ...]}}}`. Fields: `t` (°C), `ws`, `wd` (wind speed m/s, direction from, deg), `g` (gust, IFS, null past its hours), `r` (rain mm/h), `c` (cloud %), `p` (hPa), `wh`, `wp`, `wdir` (GFS-Wave), `sst` (°C, daily, carried forward). Integers with the scale in the file.

- [ ] **Step 1: Failing tests**: indices on a `SourceGrid` (lat south-to-north) and on `GLOBE` (north-to-south) land on the right cell, including across the antimeridian; `sea=True` moves a land station to the nearest finite cell and leaves it null when none within 3 cells; `write` groups by country and region and round-trips the scaled integers; a station with no region is written under `_/`.
- [ ] **Step 2–4:** run, implement, pass. `build_run(..., stations=None)` samples at each globe frame time when given records; `cycle` and `build` pass `--catalogue FILE` when present.
- [ ] **Step 5: Commit** `feat: station weather files in every forecast run`.

### Task 2: Station data files (daily)

**Files:** Create `pipeline/station_pages.py`, `tests/test_station_pages.py`; modify `pipeline/__main__.py` (`station-data`).

**Interfaces — Consumes:** `station_turns`, `table_window` (phase 8), `sky_days`, `tidal_coefficient`, `predict`, `curve`. **Produces:** `station_data(rec, entry, constants, today: date, sky, coef: dict[date, int]) -> dict` = `{"v":1, "id", "tz", "today", "has_tides", "source", "donor", "days": [{date, day_minutes, sunrise, sunset, dawn, dusk, transit, golden, blue, day_length_h, moon, solunar, coef, tides: [["HH:MM", min, height m (3 dp), 1|0], ...]}], "curve": {"from": "YYYY-MM-DD", "step_min": 10, "cm": [...]}}` — days = the calendar month of `today` in the station's zone; curve = yesterday, today, tomorrow (local), from `predict` for harmonic/model constants and `curve()` between turns otherwise. `write_station_data(catalogue, constants, today, out, sky, workers) -> dict`.

- [ ] **Step 1: Failing tests**: a harmonic station's day turns equal `station_turns` converted to local time; a 25 h day keeps 25 h of curve; a `none` station has `has_tides: false`, empty tides and no curve but full sky; the donor is named; coefficient taken from the shared map; file layout `{out}/{path}.json`.
- [ ] **Step 2–4:** run, implement, pass. Time the whole catalogue (ledger).
- [ ] **Step 5: Commit** `feat: daily station data (month of tides and sky, 3-day curve)`.

### Task 3: The station page (server side)

**Files:** Modify `web/src/pages/[cc]/[region]/[station].astro`, `web/src/stations/catalogue.ts` (`loadStationData(path)`), `web/src/styles/station.css`; create `web/src/station/format.ts` + test; e2e `web/tests/e2e/station.spec.ts`.

**Produces:** the page prints today's tides, a sun/moon card, the 30-day table (date, highs and lows, sunrise/sunset, moon, coefficient) and the source line; embeds the data as `<script type="application/json" id="st-data">`. With no data file (`STATION_DATA_DIR` missing) it keeps the phase 7 page.

- [ ] **Step 1: Failing tests**: Vitest for `format.ts` (height in m/ft, coefficient labels Low < 45 ≤ Average < 70 ≤ High < 90 ≤ Very high, moon disc fraction); e2e on New York City: 30 rows, today highlighted, source names the donor; a `none` page says "No tide predictions here".
- [ ] **Step 2–4:** run, implement, pass.
- [ ] **Step 5: Commit** `feat: station pages with tides, sun and moon`.

### Task 4: The station page (browser side)

**Files:** Create `web/src/station/chart.ts`, `web/src/station/page.ts`, `web/src/station/weather.ts`, `web/src/station/months.ts` + tests; modify the page to load `page.ts`.

**Produces:** `chartPath(day, curve, turns, size) -> {path, marks}` (curve from the embedded 10-minute heights when present, else cosine between turns); "now" line in the station's zone; day picker (the table rows); unit switch; weather strip (8 days at 3 h from `wx/latest.json` → `stations/{cc}/{region}.json`); other months and CSV from `tides/{path}.json`.

- [ ] **Step 1: Failing tests**: chart passes through every turn and spans `day_minutes`; cosine fallback is monotonic between turns; local "today" picks the right day for a viewer in another zone; weather decode from a fixture file, missing station → null; months: a month's turns from the 25-month file in local time, CSV header and row format.
- [ ] **Step 2–4:** run, implement, pass; e2e: chart drawn, clicking a row redraws, unit switch changes heights.
- [ ] **Step 5: Commit** `feat: tide chart, weather, other months and CSV on station pages`.

### Task 5: Daily page workflow and docs

**Files:** Modify `.github/workflows/site.yml` (daily cron, station-data step, DE421 cache, constants from the private bucket when set), `tests/test_workflows.py`, `docs/deploy.md`, README, spec §9.

- [ ] **Step 1: Failing workflow test**: daily schedule; downloads `catalogue/stations.json` and the tide constants (private bucket first); installs `[publish,sky]`; runs `station-data` before the build with `STATION_DATA_DIR`; still publishes changed files only.
- [ ] **Step 2–4:** implement; local dry run: station data + build + `publish-site` to `dir:` (ledger timings).
- [ ] **Step 5: Commit** `feat: daily station page workflow`.
