# Phase 3a: pipeline for the remaining globe layers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One `python -m pipeline build` writes every globe sprite family (`a`, `b`, `t`, `s`, `w`, `c`) and a full `globe.json`, matching the captured reference run 2026111306.

**Architecture:** The existing wave path (fetch → regrid → encode → pack → manifest) is generalised. Sources gain the GFS 13 km, GFS 0.25°, IFS (reduced Gaussian O1280), Mercator currents and sea temperature grids. Each family has a frame builder; `build_run` drives them chunk by chunk, so only one time step of inputs is in memory at once. Rules the reference does not publish (rain step, cloud byte, storm index, daily ocean frame) are chosen by comparing candidates against the captured sprites, then frozen as tests.

**Tech Stack:** Python 3.14, numpy, omfiles, Pillow, pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-same-sources-data-design.md` (sections 4, 5, 8, 9). Formats: `docs/wave-map-findings-and-plan.md` section 4.

Phase 3b (separate plan, after this one) puts these layers on the web globe: layer switch and pages, per-layer shading, legend, particles and readout.

## Global Constraints

- Grid 768×384, `GLOBE` in `pipeline/grid.py`; 57 frames every 3 h; chunks `[8,8,8,8,8,8,9]`; 4 columns; lossless WebP.
- Sprite channels: `a` = wind u, wind v, rain · `b` = cloud, pressure, gust · `t` = air temperature, 0, 0 · `s` = storm index, 0, 0 · `c` (one file, 8 daily frames) = current u, current v, sea temperature.
- Decodes (findings §4): wind `(b−128)×50/127` m/s · gust `b/255×60` m/s · rain `(b/255)²×64` mm/h · air temp `b/255×110−60` °C · sea temp `b/255×36−2` °C · current `(b−128)/127×2.5` m/s · pressure `940+(b−1)/254×120` hPa, 0 = none.
- Run alignment for globe run T: GFS, GFS 0.25° and GFS-Wave run T; IFS run T−6 h; currents and sea temperature the newest daily run available.
- Gusts only to hour 84 (`gustHours: 84`); later gust bytes are 0. Pressure where IFS has no frame: GFS 0.25° `pressure_msl` of run T.
- Manifest adds `pressure, gust, gustHours: 84, currents, currentEvery: 24, currentFrames: 8, storms` and `sources: {ecmwf, wave, cur, sst}`, plus peaks `wind, rain, hot, cold, gust (85 entries), low, wave, sea_hot, current`.
- Never publish a partial run; a missing required input raises `RunIncomplete`.
- `reference/` is never committed. Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **IFS 06Z/18Z runs end 138 h after T** — frames past that must take GFS pressure, not fail the run and not leave pressure 0. Test in Task 7.
2. **A file that lacks one variable** (GFS has no cloud or rain at hour 0) — that channel encodes as "none" (0), the run still builds. Test in Task 1 and Task 4.
3. **Antimeridian and poles in the reduced Gaussian regrid** — no seam at ±180°, finite values at the top and bottom rows. Test in Task 2.
4. **Ocean layers on land** — currents and sea temperature are spread 4 cells into land like waves; deep inland stays "none" (current 128, sea temp 0). Test in Task 6.
5. **Out-of-range values** (pressure below 940 hPa, gusts above 60 m/s, temperatures beyond the scale) clip to the end bytes, and the peak still reports the true value. Test in Task 3 and Task 7.

---

### Task 1: Sources for every model

**Files:**
- Modify: `pipeline/sources/openmeteo.py`
- Test: `tests/test_openmeteo_source.py`

**Interfaces:**
- Produces:
  - `MODELS: dict[str, SourceGrid | ReducedGaussian]` with `ncep_gfswave025`, `ncep_gfs013` (`SourceGrid(lat0=-89.912125, lon0=-180.0, dlat=179.82425/1535, dlon=360/3072)`), `ncep_gfs025` (`lat0=-90, lon0=-180, dlat=dlon=0.25`), `ecmwf_ifs` (`ReducedGaussian(1280)` from Task 2), `meteofrance_currents` and `meteofrance_sea_surface_temperature` (`lat0=-79.958336, lon0=-179.95833, dlat=dlon=1/12`).
  - `OpenMeteoRun(model, run, cache_dir, fetch=http_fetch, cache_run=None)`: the cache folder is `cache_dir/<cache_run or run>/<model>/`. The meta check still compares `reference_time` with `run`.
  - `OpenMeteoRun.field_or_none(variable, t) -> np.ndarray | None`: None when the run has time t but that file lacks the variable (live `.om`: `get_child_by_name` raises `ValueError`; cache: the stamp is listed for that variable in `absent.txt`, format `2026-11-13T0600: cloud_cover, precipitation`). `field()` keeps raising.
  - `OpenMeteoRun.has_time(t) -> bool` from `meta()["valid_times"]`.
  - `resolve_daily_run(model, globe_run, cache_dir, fetch) -> datetime`: when `cache_dir/<globe_run>/<model>/meta.json` exists and is completed, its `reference_time`. Otherwise the first completed run among 00Z of T's date, then the 3 days before. Raises `RunIncomplete` when none is complete.

- [ ] **Step 1: Write the failing tests**
  - `test_cache_folder_follows_cache_run`: `OpenMeteoRun("ecmwf_ifs", T-6h, tmp, cache_run=T).dir == tmp/"2026111306"/"ecmwf_ifs"`.
  - `test_absent_variable_from_cache_list_is_none`: write `absent.txt` with `2026-11-13T0600: cloud_cover`; `field_or_none("cloud_cover", T) is None`.
  - `test_absent_variable_in_om_file_is_none`: a fake reader whose `get_child_by_name` raises `ValueError` → None.
  - `test_daily_run_prefers_cached_meta`: cached meta with `reference_time 2026-11-12T00:00:00Z`, completed → 2026-11-12 00Z, and the fake fetch is never called.
  - `test_daily_run_walks_back_to_a_completed_run`: fake fetch with 404 for 11-13 and a completed meta for 11-12 → 11-12 00Z.
  - `test_daily_run_gives_up_after_four_days`: all 404 → `RunIncomplete`.
- [ ] **Step 2: Run them, expect failures:** `.venv/Scripts/python.exe -m pytest tests/test_openmeteo_source.py -q` → the new tests FAIL (missing attributes).
- [ ] **Step 3: Implement** the interfaces above. `field_or_none` reads `absent.txt` once per instance.
- [ ] **Step 4: Run** the same command → all pass.
- [ ] **Step 5: Commit** `feat: sources for GFS, IFS and Mercator models`.

### Task 2: Reduced Gaussian regrid (IFS O1280)

**Files:**
- Modify: `pipeline/regrid.py`
- Test: `tests/test_regrid.py`

**Interfaces:**
- Produces:
  - `ReducedGaussian(n: int)` (frozen dataclass): `lats()` gives 2n Gaussian latitudes, north to south, from `numpy.polynomial.legendre.leggauss(2n)`. `counts()` gives row i (0-based from the north, mirrored south of the equator) `4*(i+1)+16` points, starting at longitude 0°, step `360/count`. `offsets()` gives row starts in the flat array.
  - `regrid(src, sg, grid) -> np.ndarray`, dispatching to `regrid_bilinear` for `SourceGrid` and `regrid_reduced_gaussian` for `ReducedGaussian`. `src` for IFS is the `(1, 6599680)` array; flatten it.
  - `regrid_reduced_gaussian(src, rg, grid)`: for each globe latitude, take the two bracketing Gaussian rows (clamped at the outermost rows). In each row, interpolate linearly in longitude, wrapping. Then interpolate linearly in latitude. NaN neighbours are skipped by weight, as in `regrid_bilinear`.

- [ ] **Step 1: Write the failing tests**
  - `test_o1280_has_6599680_points`: `sum(ReducedGaussian(1280).counts()) == 6599680`.
  - `test_smooth_field_is_reproduced`: build `f = sin(lat)+cos(lat)*cos(lon-30°)` on O1280 points; the regridded globe matches f at cell centres within 1e-3 everywhere.
  - `test_no_seam_at_antimeridian`: for the same field, `|out[:, 0] - out[:, -1]|` is within the cell-to-cell gradient (< 0.02).
  - `test_poles_are_finite`: rows 0 and 383 are finite.
  - `test_missing_cells_are_skipped`: set one row's values to NaN; output stays finite and close to f.
- [ ] **Step 2: Run, expect FAIL:** `.venv/Scripts/python.exe -m pytest tests/test_regrid.py -q`.
- [ ] **Step 3: Implement** as specified, vectorised per globe row (384 rows × 768 columns).
- [ ] **Step 4: Run** → pass. Also run `tests/test_openmeteo_source.py` (it imports `ReducedGaussian`).
- [ ] **Step 5: Commit** `feat: regrid the IFS reduced Gaussian grid`.

### Task 3: Byte encodings for every quantity

**Files:**
- Modify: `pipeline/codecs.py`
- Test: `tests/test_codecs.py`

**Interfaces:**
- Produces (all take float arrays and return `uint8`; `rint`, then clip):
  - `encode_wind(ms)`: `128 + ms*127/50`, NaN → 128.
  - `encode_gust(ms)`: `ms/60*255`, NaN → 0.
  - `encode_rain(mmh)`: `sqrt(mmh/64)*255`, NaN → 0.
  - `encode_air_temp(c)`: `(c+60)/110*255`, NaN → 0.
  - `encode_sea_temp(c)`: `(c+2)/36*255`, NaN → 0.
  - `encode_current(ms)`: `128 + ms/2.5*127`, NaN → 128.
  - `encode_pressure(hpa)`: `1 + (hpa-940)/120*254`, clipped to 1–255; NaN → 0.
  - `encode_cloud(pct)`: provisional `pct/100*255`, NaN → 0; Task 4 confirms or replaces it.
  - The matching `decode_*` for each.

- [ ] **Step 1: Write the failing tests**
  - `test_round_trip_within_one_level` (parametrised over all eight): decode(encode(x)) is within one byte step of x across the scale.
  - `test_missing_values_encode_as_none`: wind and current give 128; the others give 0.
  - `test_out_of_range_clips`: pressure 930 → 1, 1070 → 255; gust 70 → 255; air temp −70 → 0, 55 → 255.
- [ ] **Step 2: Run, expect FAIL:** `.venv/Scripts/python.exe -m pytest tests/test_codecs.py -q`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → pass.
- [ ] **Step 5: Commit** `feat: byte encodings for wind, rain, cloud, pressure, gust, temperature, currents`.

### Task 4: Atmosphere frames (`a`, `b`, `t`), with rain and cloud rules chosen against the reference

**Files:**
- Create: `pipeline/atmosphere.py`
- Create: `tools/compare_reference_rules.py` (a dev tool kept in the repository; it reads `reference/`)
- Test: `tests/test_atmosphere.py`

**Interfaces:**
- Consumes: `OpenMeteoRun.field_or_none`, `regrid` (Task 2), the encoders (Task 3).
- Produces:
  - `AtmosInputs`: dataclass of native arrays or None: `u, v, rain, cloud, temp, pressure, gust`, plus `pressure_grid` and `gust_grid`, since these come from IFS or GFS 0.25°.
  - `frame_a(inp, grids) -> (384,768,3) uint8`, `frame_b(...)`, `frame_t(...)`.
  - `rain_for_frame(src, t) -> np.ndarray | None`, implementing the rain rule chosen in Step 1.
  - Wind, temperature and pressure cover every cell (no land fill).

- [ ] **Step 1: Choose the rain and cloud rules.** Write `tools/compare_reference_rules.py`. It loads the saved inputs (`reference/openmeteo-inputs/2026111306`) and the captured `globe-a0`/`globe-b0`, and prints the mean absolute byte difference per frame 0–7 for each candidate:
  - Rain: (r1) `precipitation` at t; (r2) mean of `precipitation` over t−2 h … t; (r3) value at t+1 h. Each is tried with and without `showers` added.
  - Cloud: (c1) `cloud_cover/100*255`; (c2) square-root scale.

  Run `.venv/Scripts/python.exe tools/compare_reference_rules.py rain cloud`. Expected: one candidate per quantity with a mean difference ≤ 2. Keep the lowest. If none is ≤ 2, keep the lowest and ledger a ruling with the numbers. Then check the chosen rain rule against reference `peaks.rain` for all 169 hours. That covers hours past 120, where GFS becomes 3-hourly; adjust the rule for 3-hour steps if the late hours disagree.
- [ ] **Step 2: Write the failing tests**
  - `test_wind_channels_encode_u_and_v`: constant u=10, v=−5 → bytes 153 and 115 everywhere.
  - `test_missing_rain_and_cloud_encode_none`: inputs with rain=None, cloud=None → channels 0, frame still built.
  - `test_gust_none_after_hour_84`: `frame_b` with `gust=None` → B channel 0.
  - `test_rain_rule_*`: one test pinning the chosen rule on a 3-hour synthetic series (e.g. hourly 1, 2, 3 mm → the expected frame value).
- [ ] **Step 3: Run, expect FAIL:** `.venv/Scripts/python.exe -m pytest tests/test_atmosphere.py -q`.
- [ ] **Step 4: Implement** `pipeline/atmosphere.py`. Put the chosen cloud scale into `encode_cloud` if Step 1 changed it.
- [ ] **Step 5: Run** → pass, plus `tests/test_codecs.py`.
- [ ] **Step 6: Commit** `feat: wind, rain, cloud, pressure, gust and temperature frames`.

### Task 5: Storm index (`s`)

**Files:**
- Create: `pipeline/storms.py`
- Modify: `tools/compare_reference_rules.py` (add a `storm` mode)
- Test: `tests/test_storms.py`

**Interfaces:**
- Produces: `storm_index(cape, precip, lifted_index) -> float array 0..255` on the globe grid, and `frame_s(...) -> uint8 (384,768,3)` (G and B are 0).
- Rule family (spec §8: our own rule, tuned): `index = clip(k * cape^p, 0, 255) * gate(precip)`, where `gate = clip(precip / g, 0, 1)`; optionally zero where `lifted_index > 0`.

- [ ] **Step 1: Tune.** In `compare_reference_rules.py storm`, grid-search k ∈ {0.05, 0.1, 0.2}, p ∈ {0.75, 1}, g ∈ {0.1, 0.5, 1} mm/h, with and without the lifted-index gate, against `globe-s0` frames 0–7. Print the nonzero-cell IoU and the mean absolute byte difference. Keep the best IoU, and ledger the chosen constants with the numbers. Expected: IoU ≥ 0.5. If the best is below that, ledger it; the layer still ships, as spec §8 allows.
- [ ] **Step 2: Write the failing tests:** `test_no_cape_no_storm`, `test_no_rain_no_storm`, `test_index_grows_with_cape`, `test_index_clips_at_255` (using the chosen constants).
- [ ] **Step 3: Run, expect FAIL:** `.venv/Scripts/python.exe -m pytest tests/test_storms.py -q`.
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run** → pass.
- [ ] **Step 6: Commit** `feat: thunderstorm index layer`.

### Task 6: Ocean file (`c`): currents and sea temperature, 8 daily frames

**Files:**
- Create: `pipeline/ocean.py`
- Modify: `tools/compare_reference_rules.py` (add an `ocean` mode)
- Test: `tests/test_ocean.py`

**Interfaces:**
- Consumes: `resolve_daily_run`, `fill_land` from `pipeline/waves.py`, `encode_current`, `encode_sea_temp`.
- Produces:
  - `CURRENT_FRAMES = 8`, `CURRENT_EVERY = 24`. Frame k is for globe hour 24k (k = 0..7); the reference peaks change exactly at hours 24, 48 … 168.
  - `ocean_frame(u, v, sst, sg) -> uint8 (384,768,3)`: regrid, `fill_land` 4 passes, encode.
  - `daily_fields(src_cur, src_sst, globe_run, k) -> (u, v, sst)`: native arrays from the rule chosen in Step 1.
  - `pack_ocean(frames) -> Image` with 4 columns × 2 rows (reuse `pack_chunk`).

- [ ] **Step 1: Choose the daily rule.** In `compare_reference_rules.py ocean`, compare the captured `globe-c` (all 8 frames are captured) over sea cells with:
  - (d1) the snapshot at T+24k;
  - (d2) the mean over the calendar day containing T+24k;
  - (d3) the mean over T+24k ± 12 h.

  Sea temperature is 6-hourly, so use its nearest time for d1 and the mean of the day's four values for d2/d3. Expected: one rule at mean difference ≤ 2 per channel; keep the best and ledger it.
- [ ] **Step 2: Write the failing tests:** `test_land_is_filled_near_coast_and_none_inland` (current 128, sea temp 0 deep inland), `test_eight_frames_four_by_two`, and `test_daily_rule_*` pinning the chosen rule on a synthetic hourly series.
- [ ] **Step 3: Run, expect FAIL:** `.venv/Scripts/python.exe -m pytest tests/test_ocean.py -q`.
- [ ] **Step 4: Implement.** Read hourly current files one at a time and keep running sums, so at most one native field pair is in memory.
- [ ] **Step 5: Run** → pass.
- [ ] **Step 6: Commit** `feat: daily currents and sea temperature file`.

### Task 7: `build_run`, peaks, manifest, CLI

**Files:**
- Modify: `pipeline/build.py`, `pipeline/__main__.py`, `pipeline/waves.py` (move the peak helper out)
- Create: `pipeline/peaks.py`
- Test: `tests/test_build.py`, `tests/test_peaks.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `peak(field_on_globe, mode="max"|"min", value=lambda x: x) -> [value(1 dp), lat(2 dp), lon(2 dp)]`, taken over the regridded field before rounding and land fill (the wave rule from phase 1). Series: wind = max `hypot(u,v)`, rain max, hot = max temperature, cold = min temperature, gust max (hours 0–84), low = min pressure, wave (as now), sea_hot = max sea temperature, current = max `hypot(u,v)`.
  - `hourly(frame_peaks, every, hours)`: entry h = `frame_peaks[h // every]`, so 169 entries for 3-hourly and daily frames alike, and 85 for gust.
  - `build_run(run, cache_dir, out_dir, sources=None) -> Path` writes `globe-{a,b,t,s,w}{0..6}.webp`, `globe-c.webp` and `globe.json` into the run folder, with the same tmp-and-swap behaviour as `build_waves`. `sources` is an optional dict of model → `OpenMeteoRun` for tests. `build_waves` is removed and the CLI `build` calls `build_run`.
  - Completeness check before writing anything. Required: wave, GFS 13 km and GFS 0.25° at every frame time; IFS gust at frames ≤ 84 h; the currents and sea temperature runs cover T … T+168 h. IFS pressure is optional per frame, with GFS 0.25° filling the gaps. A missing required input raises `RunIncomplete`, naming up to 5 items.

- [ ] **Step 1: Write the failing tests**
  - `test_peaks.py`: `test_hourly_repeats_each_frame` (57 frames → 169 entries), `test_gust_series_stops_at_84` (85 entries), `test_min_peak_for_low_and_cold`, and `test_peak_reports_true_value_beyond_byte_scale` (pressure 935.3 reported as 935.3).
  - `test_build.py` (fake sources, small in-memory grids as in the existing tests):
    - `test_writes_every_family`: 7 chunks each of a, b, t, s, w, plus `globe-c.webp`.
    - `test_manifest_flags_and_sources`: `gustHours == 84`, `currentFrames == 8`, `currentEvery == 24`, and `sources` has `ecmwf` = T−6 h, `wave` = T, plus `cur` and `sst`.
    - `test_ifs_gap_falls_back_to_gfs_pressure`: IFS lacks hour 141 → that frame's pressure equals the GFS-derived byte, not 0.
    - `test_missing_gfs_frame_refuses_to_build`: `RunIncomplete`, and no run folder.
- [ ] **Step 2: Run, expect FAIL:** `.venv/Scripts/python.exe -m pytest tests/test_build.py tests/test_peaks.py -q`.
- [ ] **Step 3: Implement.** Loop chunk by chunk; per frame time, read each input once, build all five frames, then drop the inputs.
- [ ] **Step 4: Run** → pass, then the whole suite: `.venv/Scripts/python.exe -m pytest -q -m "not reference"`.
- [ ] **Step 5: Commit** `feat: build every globe layer in one run`.

### Task 8: Reference test for every layer, dev data, spec results

**Files:**
- Modify: `tests/test_reference_run.py` (switch to `build_run`, add the new families)
- Modify: `docs/superpowers/specs/2026-11-14-same-sources-data-design.md` §9 (results)
- Regenerate: `web/public/wx/` (git-ignored dev data)

**Interfaces:**
- Consumes: `build_run`.

- [ ] **Step 1: Extend the reference tests** (module-scoped single build):
  - `test_chunk0_wind_rain_match` (a0: mean byte difference ≤ 2 per channel, all cells).
  - `test_chunk0_cloud_pressure_gust_match` (b0: the same).
  - `test_chunk0_temperature_matches` (t0).
  - `test_ocean_file_matches` (c, all 8 frames, sea cells).
  - `test_storm_overlap` (s0: IoU ≥ the value ledgered in Task 5).
  - `test_all_peaks_match`: every series, every hour, position within 2 cells and value within 0.5. Report the `low` hours 141–168 separately; they test the GFS pressure filler, so if they fail, ledger the numbers rather than loosening the others.
  - Keep the existing wave tests.
- [ ] **Step 2: Run:** `.venv/Scripts/python.exe -m pytest tests/test_reference_run.py -q` → pass (thresholds as above). A real miss goes to superpowers:systematic-debugging, not to looser thresholds.
- [ ] **Step 3: Regenerate dev data:** `.venv/Scripts/python.exe -m pipeline build --run 2026111306 --cache reference/openmeteo-inputs --out web/public/wx --latest`. Expected: the folder lists 36 sprite files and `globe.json`. Then `cd web && npm test && npx playwright test` → still green (the web reads only `w` so far).
- [ ] **Step 4: Record results** in spec §9 as "Phase 3a results": the chosen rules, the measured differences per family, and the peak agreement.
- [ ] **Step 5: Commit** `test: reference comparison for every globe layer; phase 3a results`.
