# Phase 8: Tide Engine, Constants, Astronomy and Tide Tables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Predict high and low waters for every catalogue station from NOAA constants, NOAA subordinate offsets or a global tide model, compute sun, moon, solunar and coefficient data, and publish a 25-month tide table per station every month.

**Architecture:** `pipeline/tide_predict.py` is a harmonic engine (Schureman arguments and nodal factors for NOAA's 37 constituents and the global models' set). `pipeline/tide_constants.py` assembles one constants record per station following the spec §6 rules and writes `tide-constants.json`; a model reader samples EOT20 now and FES2022 later (same output; the FES2022 run happens on the owner's machine). `pipeline/sky.py` uses skyfield with JPL DE421. `pipeline/tide_tables.py` writes `tides/{path}.json` per station, run monthly by `.github/workflows/tides.yml`.

**Tech Stack:** Python 3.12+ / numpy, h5py (`[tides]`), skyfield 1.55 + jplephem (new `[sky]` extra), boto3.

**Spec:** `docs/superpowers/specs/2026-11-14-same-sources-data-design.md` §4, §6 ("Tides", "Astronomy"), §7, §8, §9 ("Tide test"), §10 step 8.

## Global Constraints

- Heights in metres from mean sea level, astronomical tide only. Times in UTC inside files; pages convert.
- Constants rules (spec §6): NOAA harmonic station → its constants; NOAA subordinate station → offsets on its reference station only when that station is within 1,000 km, else the model; place within 5 km of a usable NOAA station → that station's tide (donor named); everything else → model at the place, nearest ocean cell within 20 km when the point falls on land; nothing within 20 km → no tides (`has_tides` false).
- The model is EOT20 (CC BY 4.0) until the owner supplies FES2022; every output names its source. FES2022 never enters the repository or a runner: `tools/fes2022_constants.py` runs on the owner's machine and writes the same file format.
- NOAA data is public domain; pages say "not NOAA's official predictions". Small NOAA API responses may be committed as test fixtures. Values from the reference site are never copied into the repository; reference comparisons read the git-ignored capture at test time.
- Tide tables cover 12 months either side of the run month (25 months).
- Python file I/O passes `encoding="utf-8"`.

## Review Focus

1. **Subordinate stations whose reference is a subordinate or missing**: fall back to the model, never crash or loop.
2. **Daylight-saving days in the station's zone** (23 h and 25 h days, the repeated hour): sky events and day boundaries come out right.
3. **Polar day and night** (no sunrise, no moonset that day): fields are null, not wrong times.
4. **Diurnal or mixed tides with a "missing" turn in a day** and shallow-water double highs: extrema detection neither drops real turns nor reports ripples.
5. **A station on land more than 20 km from model ocean**: `has_tides` false and no tide file, no NaN.

---

### Task 1: Harmonic engine

**Files:** Create `pipeline/tide_predict.py`, `tests/test_tide_predict.py`; fixtures `tests/fixtures/noaa/8518750-harcon.json`, `8518750-hilo-2026-11.json` (MSL), `8518750-hourly-2026-11-01.json`, `8518750-hilo-mllw-2026-11.json`, `8518750-datums.json`.

**Interfaces — Produces:** `CONSTITUENTS: dict[str, Constituent]` (37 NOAA names plus EOT20's, upper-case NOAA spelling); `predict(times: np.ndarray[datetime64], cons: list[tuple[str, float, float]]) -> np.ndarray` (name, amplitude m, Greenwich phase lag deg; heights m about MSL); `extrema(start: datetime, end: datetime, cons, step_min: int = 6) -> list[Turn]` with `Turn = (time: datetime, height: float, kind: "high" | "low")`.

- [ ] **Step 1: Failing tests**: `test_hourly_heights_match_noaa` (Battery, 72 hourly NOAA MSL predictions, max abs difference ≤ 0.01 m); `test_turns_match_noaa_hilo` (Battery, November 2026: same count, each turn within 2 min and 0.01 m); `test_unknown_constituent_is_an_error`; `test_double_high_ripple_is_not_two_turns` (synthetic M2 + M4 + M6 with a shoulder: turns are real local extrema only, minimum 2 h apart).
- [ ] **Step 2: Run** `pytest tests/test_tide_predict.py` — Expected: FAIL.
- [ ] **Step 3: Implement.** V from Doodson numbers on (T, s, h, p, N′, p₁) at each time; u and f from Schureman formulas by group (O1, K1, J1, OO1, M1, K2, L2, Mf, Mm, M2 family and products for compounds); f and u evaluated per time (cheap). Extrema: sample every `step_min`, sign change of the first difference, refine with a parabola through three samples.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat: harmonic tide engine for NOAA's 37 constituents`.

### Task 2: Subordinate stations and curves

**Files:** Modify `pipeline/tide_predict.py`, `tests/test_tide_predict.py`; fixtures `8517921-offsets.json`, `8517921-hilo-mllw-2026-11.json`.

**Interfaces — Produces:** `Offsets(time_high_min, time_low_min, height_high, height_low, kind: "R" | "A")`; `subordinate(ref_turns: list[Turn], off: Offsets, ref_msl_above_mllw: float) -> list[Turn]` (MSL heights); `curve(turns: list[Turn], times) -> np.ndarray` (cosine between turns).

- [ ] **Step 1: Failing tests**: `test_subordinate_matches_noaa_on_mllw` (Williamsburg 8517921 from the Battery, November 2026, on MLLW: every turn within 1 min and 0.01 m of NOAA); `test_subordinate_msl_heights` (our MSL rule: `h = (h_ref + D)·r − D·(r_high + r_low)/2` for ratio offsets, `h_ref + a − (a_high + a_low)/2` for additive; D = reference MSL − MLLW); `test_curve_passes_through_turns_and_is_monotonic_between`.
- [ ] **Step 2–4:** run, implement, pass.
- [ ] **Step 5: Commit** `feat: NOAA subordinate offsets and tide curves from turns`.

### Task 3: Constants for every station

**Files:** Create `pipeline/tide_constants.py`, `pipeline/tide_model.py` (EOT20 reader and sampler; FES2022 reader with the same interface), `tools/fes2022_constants.py`, `tests/test_tide_constants.py`; modify `pipeline/__main__.py` (`tide-constants`), `.github/workflows/static.yml`.

**Interfaces — Produces:** `fetch_noaa(stations, cache: Path, fetch=http_fetch) -> dict` (harcon for type R, offsets for type S, MSL−MLLW datum for R; cached per station; polite: one request at a time with retries); `ModelSampler.sample(lat, lon) -> list[(name, amp, phase)] | None` (nearest ocean cell within 20 km); `assign(records, noaa, model) -> dict[id, entry]` where entry is `{"kind": "harmonic" | "subordinate" | "donor" | "model" | "none", ...}`; output `tide-constants.json` `{"model": "EOT20 …", "built": iso, "stations": {id: entry}}`.

- [ ] **Step 1: Failing tests** with fake fetch and a tiny synthetic model grid: harmonic, subordinate within 1,000 km, subordinate whose reference is 1,200 km away → model, subordinate whose reference is itself subordinate or missing → model (Review Focus 1), donor place, land point 10 km from ocean → nearest ocean cell, 30 km → `none` (Review Focus 5); `fetch_noaa` reuses its cache; FES2022 reader reads a synthetic netCDF written by h5py in the test.
- [ ] **Step 2–4:** run, implement, pass. Then build the real file (EOT20 from `eot20/`), record counts per kind and size in the ledger.
- [ ] **Step 5: Commit** `feat: tide constants for every station (NOAA, offsets, donors, EOT20)`.

### Task 4: Sun, moon, solunar and coefficient

**Files:** Create `pipeline/sky.py`, `tests/test_sky.py`; modify `pyproject.toml` (`sky = ["skyfield==1.55"]`).

**Interfaces — Produces:** `SkyDay` dict per (station, local date): `sunrise, sunset, transit, dawn, dusk` (civil), `golden: [[from, to], …]`, `blue: [[from, to], …]`, `day_length_h`, `moon: {phase_angle, illum, name, rise, set, distance_km}`, `solunar: {major: [[from, to]…], minor: […]}`; times as local "HH:MM" plus minutes since local midnight; null when an event does not happen (Review Focus 3). `sky_days(lat, lon, tz, first: date, n: int, eph) -> list[SkyDay]`; `tidal_coefficient(day: date, eph) -> int` (20–120, French formula from the Moon's and Sun's declination and distance).

- [ ] **Step 1: Failing tests**: Tromsø in December (no sunrise → null) and June (no sunset); a New York DST change day (2026-11-01: 25 h, sunrise after the change); solunar majors centred on lunar transit and anti-transit (2 h), minors on moonrise and moonset (1 h); coefficient range 20–120 and highest near the equinox spring tides. Reference test (marker `reference`, reads the captured station page at test time): New York City, November 2026, sunrise and sunset within 1 min, moonrise and moonset within 2 min, illumination within 1 %, phase names equal; coefficient within the tolerance we measure (ledger it).
- [ ] **Step 2–4:** run, implement, pass. DE421 is downloaded once by skyfield's loader into a cache folder (CI caches it).
- [ ] **Step 5: Commit** `feat: sun, moon, solunar periods and tidal coefficient from DE421`.

### Task 5: Monthly tide tables

**Files:** Create `pipeline/tide_tables.py`, `tests/test_tide_tables.py`, `.github/workflows/tides.yml`; modify `pipeline/__main__.py` (`tide-tables`), `tests/test_workflows.py`, `docs/deploy.md`, README, spec §9.

**Interfaces — Produces:** `station_turns(entry, constants, start, end) -> list[Turn]`; `write_tables(catalogue, constants, month: date, out: Path) -> dict` writing `tides/{path}.json` = `{"v":1, "id", "source", "donor": {name, path} | null, "datum": "MSL", "from", "to", "turns": [[minutes since from, height cm, 1 high | 0 low], …]}`; stations with `kind: none` get no file and are listed in `tides/index.json` as without tides.

- [ ] **Step 1: Failing tests**: a harmonic station's table spans exactly 25 months and matches `extrema`; a donor place's table equals its donor's with its own id and the donor named; a subordinate table matches `subordinate`; a `none` station gets no file; heights in whole centimetres; file size of a semidiurnal station under 40 KB gzip.
- [ ] **Step 2–4:** run, implement, pass. Time the whole catalogue locally; the workflow (`tides.yml`, monthly on the 1st at 02:00 UTC plus `workflow_dispatch`) downloads `catalogue/stations.json` and `catalogue/tide-constants.json`, builds, uploads `tides/` with `public, max-age=86400`.
- [ ] **Step 5: Commit** `feat: monthly 25-month tide tables for every station`.

**Spec §9 "Tide test" (New York City within 2 min and 2 cm of the capture):** the captured New York City turns are about 20 min and 6 cm from NOAA's Battery prediction, so the reference does not use the Battery there; it uses FES2022 at the place. The test is written now (marker `reference`) and runs only when `tide-constants.json` was built from FES2022; with EOT20 it is skipped and the EOT20 result is recorded in the ledger instead.
