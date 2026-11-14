# Phase 1: Pipeline Core (wave sprites) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python command that reads one GFS-Wave run from Open-Meteo's public bucket and writes the globe's wave sprites and manifest in the reference format, proven against the captured reference run.

**Architecture:** A small Python package, `pipeline/`. A source class returns native grids per variable and valid time (from a local cache, downloading whole files when missing). Pure functions regrid to the globe grid, encode to bytes and pack frames into lossless WebP sprites. A CLI ties them together and writes a run folder. Later phases add layers by adding variables, not by changing this structure.

**Tech Stack:** Python 3.12+, numpy, omfiles (Open-Meteo `.om` reader), Pillow (lossless WebP), pytest. No scipy.

**Spec:** `docs/superpowers/specs/2026-11-14-same-sources-data-design.md` (sections 4, 5, 9). Formats: `docs/wave-map-findings-and-plan.md` section 4.

## Global Constraints

- Never commit anything under `reference/` (git-ignored: third-party code and gigabytes of inputs). Tests that need it skip when it is absent.
- Never fetch data files from thetidechart.com. The only network source is `https://openmeteo.s3.amazonaws.com`.
- Write all code fresh; do not copy code from `reference/thetidechart-capture/`.
- Never publish a partial run: any missing input raises before any output file is written.
- Downloads go to `<name>.part` and are renamed on completion.
- Globe grid, exactly: `w=768, h=384, north=89.7364, west=-179.82422, dlon=0.46875, dlat=0.468597`. Cell (x, y): `lon = west + x*dlon`, `lat = north - y*dlat`.
- Frames: `every=3` h, `hours=168`, `frames=57`, `cols=4`, `chunks=[8,8,8,8,8,8,9]`. Frame `j` of a chunk sits at column `j % 4`, row `j // 4`.
- Work on branch `phase-1-pipeline-core`, not `main`. Commit messages end with `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

Rules measured against the captured reference frame on 2026-11-14 (they are facts, not choices):
- Regridding is bilinear on the native grid, ignoring missing cells, then rounded to the nearest byte: 99.8 % of sea cells match the reference byte exactly. Nearest-cell sampling matches only 73 %.
- Wave vector = direction the waves travel **toward** (`wave_direction + 180°`), x = east, y = north, length = `wave_period / 25`. Median direction error against the reference: 0.44°.
- Open-Meteo grids are stored south to north, west to east: GFS-Wave is `(721, 1440)`, `lat0=-90`, `lon0=-180`, step `0.25`. Land is `NaN`.
- Peaks: for hour `h`, use frame `h // 3`; the value is the highest globe cell of the **regridded** field (reference hour 0: `[13.9, 44.28, -140.92]`). *Corrected during Task 8: the plan first said "maximum of the native grid", which matched only 60 % of reference frames; the regridded maximum matches all 57. Tasks 6 and 8 below still show the original test text; the code and tests in the repository follow this corrected rule.*

## Review Focus

1. A valid time missing from the bucket run (run still uploading) → `RunIncomplete` naming the model and time; no output written.
2. Target longitudes at the antimeridian (x = 0 and x = 767) → values interpolated across the ±180° seam, never `NaN` over open sea.
3. A globe cell whose four source neighbours are all land → `NaN` out of the regrid, no divide-by-zero warning, and byte 0 / (128,128) after encoding.
4. Wave height above 16 m or period above 25 s → clipped to byte 255 / unit length, never wrapped.
5. A download interrupted mid-file → no file with the final name exists; the next run downloads it again.

---

### Task 1: Project scaffold and globe grid

**Files:**
- Create: `pyproject.toml`, `pipeline/__init__.py`, `pipeline/grid.py`, `tests/test_grid.py`, `README.md` (replace the placeholder)

**Interfaces:**
- Produces:
  - `pipeline.grid.GLOBE: GlobeGrid` (frozen dataclass: `w, h, north, west, dlon, dlat`)
  - `GlobeGrid.lons() -> np.ndarray` shape `(768,)`, `GlobeGrid.lats() -> np.ndarray` shape `(384,)` north to south
  - `GlobeGrid.cell_of(lat: float, lon: float) -> tuple[int, int]` returning `(y, x)` of the nearest cell, x wrapped
  - `GlobeGrid.manifest_fields() -> dict` with keys `w, h, north, west, dlon, dlat`

- [ ] **Step 1: Create the branch and commit what exists**

```bash
git checkout -b phase-1-pipeline-core
git add .gitignore docs tools
git commit -m "docs: design specs, findings and reference-input saver"
```
Verify `git status --short` shows nothing from `reference/` or `.superpowers/`.

- [ ] **Step 2: Write `pyproject.toml`**

Project name `threedweather-pipeline`, `requires-python = ">=3.12"`, dependencies `numpy`, `omfiles`, `pillow`; optional group `dev` with `pytest`. Package: `pipeline`. Pytest config: `testpaths = ["tests"]`, marker `reference: needs the local reference/ folder`. Create `.venv` and `pip install -e ".[dev]"`.

- [ ] **Step 3: Write the failing test**

```python
from pipeline.grid import GLOBE

def test_grid_axes():
    assert (GLOBE.w, GLOBE.h) == (768, 384)
    assert GLOBE.lons()[0] == -179.82422 and abs(GLOBE.lons()[-1] - 179.70703) < 1e-4
    assert GLOBE.lats()[0] == 89.7364 and abs(GLOBE.lats()[-1] - (-89.736251)) < 1e-4

def test_cell_of_reference_peak():
    assert GLOBE.cell_of(44.25, -141.0) == (97, 83)      # native max of the reference run
    assert abs(GLOBE.lats()[97] - 44.28) < 0.01 and abs(GLOBE.lons()[83] - (-140.92)) < 0.01

def test_cell_of_wraps_longitude():
    assert GLOBE.cell_of(0.0, 179.95)[1] == 0
```

- [ ] **Step 4: Run** `python -m pytest tests/test_grid.py -v` — expected: FAIL, module not found.
- [ ] **Step 5: Implement `pipeline/grid.py`** to the interface above.
- [ ] **Step 6: Run the tests** — expected: 3 passed.
- [ ] **Step 7: README and commit.** README: one paragraph on what the project is, the data credits line from spec section 4, and how to run tests. `git commit -m "feat: project scaffold and globe grid"`.

### Task 2: Byte codecs for waves

**Files:**
- Create: `pipeline/codecs.py`, `tests/test_codecs.py`

**Interfaces:**
- Produces:
  - `encode_wave_height(m: np.ndarray) -> np.ndarray` uint8: `rint(sqrt(clip(m, 0, 16) / 16) * 255)`, `NaN -> 0`
  - `decode_wave_height(b: np.ndarray) -> np.ndarray` float: `(b / 255) ** 2 * 16`
  - `wave_vector(direction_from_deg: np.ndarray, period_s: np.ndarray) -> tuple[np.ndarray, np.ndarray]` returning `(vx_east, vy_north)` floats with length `clip(period, 0, 25) / 25`, `NaN` where either input is `NaN`
  - `encode_vector(vx: np.ndarray, vy: np.ndarray) -> tuple[np.ndarray, np.ndarray]` uint8 each: `rint(128 + 127 * clip(v, -1, 1))`, `NaN -> 128`

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
from pipeline.codecs import encode_wave_height, decode_wave_height, wave_vector, encode_vector

def test_height_reference_value():
    assert encode_wave_height(np.array([13.82]))[0] == 237        # reference frame max
    assert abs(decode_wave_height(np.array([237]))[0] - 13.82) < 0.01

def test_height_clips_and_handles_nan():
    out = encode_wave_height(np.array([-1.0, 0.0, 16.0, 40.0, np.nan]))
    assert out.tolist() == [0, 0, 255, 255, 0] and out.dtype == np.uint8

def test_height_roundtrip_within_one_byte():
    b = np.arange(256, dtype=np.uint8)
    assert (encode_wave_height(decode_wave_height(b)) == b).all()

def test_vector_points_where_waves_travel():
    vx, vy = wave_vector(np.array([270.0, 0.0]), np.array([10.0, 25.0]))   # from west; from north
    g, b = encode_vector(vx, vy)
    assert (g[0], b[0]) == (179, 128)     # travels east, length 0.4
    assert (g[1], b[1]) == (128, 1)       # travels south, length 1

def test_vector_clips_long_period_and_nan():
    vx, vy = wave_vector(np.array([180.0, np.nan]), np.array([60.0, 8.0]))
    g, b = encode_vector(vx, vy)
    assert (g[0], b[0]) == (128, 255) and (g[1], b[1]) == (128, 128)
```

- [ ] **Step 2: Run** `python -m pytest tests/test_codecs.py -v` — expected: FAIL, module not found.
- [ ] **Step 3: Implement `pipeline/codecs.py`** to the interface above.
- [ ] **Step 4: Run the tests** — expected: 5 passed.
- [ ] **Step 5: Commit** `feat: wave height and vector byte codecs`.

### Task 3: Bilinear regridding that ignores missing cells

**Files:**
- Create: `pipeline/regrid.py`, `tests/test_regrid.py`

**Interfaces:**
- Consumes: `GlobeGrid` from Task 1.
- Produces:
  - `SourceGrid` frozen dataclass: `lat0: float, lon0: float, dlat: float, dlon: float, wrap: bool = True` (row 0 = `lat0`, increasing northward)
  - `regrid_bilinear(src: np.ndarray, sg: SourceGrid, grid: GlobeGrid) -> np.ndarray` float32 `(grid.h, grid.w)`, row 0 = north

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np, warnings
from pipeline.grid import GLOBE
from pipeline.regrid import SourceGrid, regrid_bilinear

SG = SourceGrid(lat0=-90.0, lon0=-180.0, dlat=0.25, dlon=0.25)
LAT = -90 + 0.25 * np.arange(721)[:, None] + np.zeros((1, 1440))
LON = -180 + 0.25 * np.arange(1440)[None, :] + np.zeros((721, 1))

def test_linear_field_is_reproduced():
    out = regrid_bilinear(LAT.astype(np.float32), SG, GLOBE)
    assert out.shape == (384, 768)
    assert np.allclose(out[:, 5], GLOBE.lats(), atol=1e-3)

def test_wraps_across_antimeridian():
    out = regrid_bilinear(np.cos(np.radians(LON)).astype(np.float32), SG, GLOBE)
    assert np.isfinite(out).all()
    assert np.allclose(out[100, [0, 767]], np.cos(np.radians(GLOBE.lons()[[0, 767]])), atol=1e-3)

def test_missing_cells_are_ignored_not_spread():
    src = np.ones((721, 1440), np.float32); src[300:340, 500:560] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("error")                      # no divide-by-zero warnings
        out = regrid_bilinear(src, SG, GLOBE)
    y, x = GLOBE.cell_of(-90 + 0.25 * 320, -180 + 0.25 * 530)
    assert np.isnan(out[y, x])                              # all four neighbours missing
    assert np.allclose(out[np.isfinite(out)], 1.0, atol=1e-6)  # partial neighbours use valid ones only
```

- [ ] **Step 2: Run** `python -m pytest tests/test_regrid.py -v` — expected: FAIL, module not found.
- [ ] **Step 3: Implement `regrid_bilinear`.** Compute fractional source indices for every target cell; take the four neighbours (column index modulo the width when `wrap`, row index clamped); weight each by its bilinear weight times a 0/1 validity mask; divide by the summed weight where it is above zero, else `NaN`.
- [ ] **Step 4: Run the tests** — expected: 3 passed.
- [ ] **Step 5: Commit** `feat: NaN-aware bilinear regridding`.

### Task 4: Open-Meteo run source

**Files:**
- Create: `pipeline/sources/__init__.py`, `pipeline/sources/openmeteo.py`, `tests/test_openmeteo_source.py`

**Interfaces:**
- Consumes: `SourceGrid` from Task 3.
- Produces:
  - `MODELS: dict[str, SourceGrid]` with `"ncep_gfswave025": SourceGrid(-90.0, -180.0, 0.25, 0.25)`
  - `class RunIncomplete(Exception)`
  - `class OpenMeteoRun(model: str, run: datetime, cache_dir: Path, fetch: Callable[[str, Path], None] = http_fetch)`
    - `.source_grid -> SourceGrid`
    - `.meta() -> dict` (the run's `meta.json`, cached as `<cache_dir>/<model>/meta.json`)
    - `.field(variable: str, valid_time: datetime) -> np.ndarray` float32, native shape
  - `http_fetch(url: str, dest: Path) -> None` (writes `dest.part`, then renames)
  - URL: `https://openmeteo.s3.amazonaws.com/data_spatial/{model}/{run:%Y/%m/%d/%H%M}Z/{name}`; file names `%Y-%m-%dT%H%M.om`

`field` looks in this order, matching the layout `tools/save_reference_inputs.py` already writes:
1. `<cache_dir>/<model>/<variable>/<stamp>.npz` — keys `data`, `scale`, `nan`, `kind`; if `kind == "int16"`, value = `data / scale` with `data == nan` → `NaN`; else `data` as is.
2. `<cache_dir>/<model>/<stamp>.om` — `omfiles.OmFileReader(path).get_child_by_name(variable)[:]`.
3. Otherwise check `meta()`: if the valid time (formatted `%Y-%m-%dT%H:%MZ`) is not in `valid_times`, the variable is not in `variables`, or `completed` is false, raise `RunIncomplete` naming model, variable and time. Else `fetch` the `.om` to path 2 and read it.

- [ ] **Step 1: Write the failing tests** (no network: a fake `fetch` writes fixture files)

```python
def test_reads_packed_npz(tmp_path): ...
    # write ncep_gfswave025/wave_height/2026-11-13T0600.npz with data=[[10, 32767]], scale=10.0, nan=32767, kind="int16"
    # assert field(...) equals [[1.0, nan]] and dtype float32

def test_missing_valid_time_raises_run_incomplete(tmp_path): ...
    # meta.json has completed=true, valid_times=["2026-11-13T06:00Z"], variables=["wave_height"]
    # field("wave_height", 09:00) raises RunIncomplete whose message contains "ncep_gfswave025" and "2026-11-13T09:00Z"
    # the fake fetch was not asked for any .om file

def test_incomplete_run_raises(tmp_path): ...            # completed=false -> RunIncomplete

def test_downloads_once_then_uses_cache(tmp_path): ...
    # fake fetch copies a tiny .om written with omfiles.OmFileWriter; call field twice; fetch called once for the .om

def test_http_fetch_leaves_no_file_on_failure(tmp_path, monkeypatch): ...
    # urlopen yields some bytes then raises; assert dest does not exist afterwards
```

- [ ] **Step 2: Run** `python -m pytest tests/test_openmeteo_source.py -v` — expected: FAIL, module not found.
- [ ] **Step 3: Implement `pipeline/sources/openmeteo.py`** to the interface above. `http_fetch` uses `urllib.request` with a 120 s timeout and 1 MiB chunks.
- [ ] **Step 4: Run the tests** — expected: 5 passed.
- [ ] **Step 5: Commit** `feat: Open-Meteo bucket run source with local cache`.

### Task 5: Sprite packing

**Files:**
- Create: `pipeline/sprites.py`, `tests/test_sprites.py`

**Interfaces:**
- Produces:
  - Constants `EVERY = 3`, `HOURS = 168`, `FRAMES = 57`, `COLS = 4`, `CHUNKS = [8, 8, 8, 8, 8, 8, 9]`
  - `chunk_frames(chunk: int) -> range` (global frame indices in that chunk; chunk 6 → `range(48, 57)`)
  - `pack_chunk(frames: list[np.ndarray]) -> PIL.Image.Image` — each frame uint8 `(384, 768, 3)`; image is `3072 × 384*ceil(n/4)`, unused cells black
  - `save_sprite(img: PIL.Image.Image, path: Path) -> None` — WebP `lossless=True, quality=100, method=6, exact=True`, written via `.part`
  - `unpack_frame(img: PIL.Image.Image, j: int) -> np.ndarray` uint8 `(384, 768, 3)`

- [ ] **Step 1: Write the failing tests**

```python
def test_chunk_ranges():
    assert list(chunk_frames(0)) == list(range(0, 8)) and list(chunk_frames(6)) == list(range(48, 57))

def test_layout_and_lossless_roundtrip(tmp_path):
    rng = np.random.default_rng(0)
    frames = [rng.integers(0, 256, (384, 768, 3), dtype=np.uint8) for _ in range(9)]
    img = pack_chunk(frames); assert img.size == (3072, 1152)
    save_sprite(img, tmp_path / "globe-w6.webp")
    back = Image.open(tmp_path / "globe-w6.webp")
    assert all((unpack_frame(back, j) == frames[j]).all() for j in range(9))
    assert not (tmp_path / "globe-w6.webp.part").exists()

def test_eight_frames_make_two_rows():
    assert pack_chunk([np.zeros((384, 768, 3), np.uint8)] * 8).size == (3072, 768)
```

- [ ] **Step 2: Run** — expected: FAIL, module not found.
- [ ] **Step 3: Implement `pipeline/sprites.py`.**
- [ ] **Step 4: Run the tests** — expected: 3 passed.
- [ ] **Step 5: Commit** `feat: lossless WebP sprite packing`.

### Task 6: Wave frames, land fill and peaks

**Files:**
- Create: `pipeline/waves.py`, `tests/test_waves.py`

**Interfaces:**
- Consumes: `OpenMeteoRun.field`, `regrid_bilinear`, `encode_wave_height`, `wave_vector`, `encode_vector`, `GLOBE`.
- Produces:
  - `fill_land(field: np.ndarray, passes: int = 4) -> np.ndarray` — each pass gives every `NaN` cell with at least one valid 8-neighbour the mean of its valid neighbours (columns wrap); cells still `NaN` after the passes stay `NaN`
  - `wave_frame(height: np.ndarray, period: np.ndarray, direction: np.ndarray, sg: SourceGrid) -> np.ndarray` uint8 `(384, 768, 3)`: R = height, G = vx, B = vy
  - `wave_peak(height_native: np.ndarray, sg: SourceGrid) -> list[float]` → `[round(max, 1), round(cell_lat, 2), round(cell_lon, 2)]` using `GLOBE.cell_of` on the native maximum's position
  - `frame_time(run: datetime, j: int) -> datetime` = `run + 3 h * j`

Order inside `wave_frame`: compute `(vx, vy)` on the native grid, regrid height, vx and vy separately, `fill_land` each, then encode. Interpolating components (not angles) is what keeps directions correct across 0°/360°.

- [ ] **Step 1: Write the failing tests**

```python
def test_fill_land_extends_coast_only():
    f = np.full((10, 10), np.nan, np.float32); f[:, 0] = 2.0
    out = fill_land(f, passes=4)
    # 4 passes reach columns 1-4 directly and 9-6 through the longitude wrap; column 5 stays empty
    assert np.allclose(out[:, 1:5], 2.0) and np.isnan(out[:, 5]).all() and (out[:, 0] == 2.0).all()

def test_wave_frame_channels():
    h = np.full((721, 1440), 9.0, np.float32); p = np.full_like(h, 10.0); d = np.full_like(h, 270.0)
    f = wave_frame(h, p, d, MODELS["ncep_gfswave025"])
    assert f.shape == (384, 768, 3) and f.dtype == np.uint8
    assert (f[..., 0] == 191).all()                  # sqrt(9/16)*255 = 191.25
    assert (f[..., 1] == 179).all() and (f[..., 2] == 128).all()   # east, length 0.4 -> 128 + 50.8

def test_direction_seam_does_not_cancel():
    h = np.ones((721, 1440), np.float32); p = np.full_like(h, 25.0)
    d = np.where(np.arange(1440)[None, :] % 2 == 0, 359.0, 1.0).astype(np.float32) + np.zeros_like(h)
    f = wave_frame(h, p, d, MODELS["ncep_gfswave025"])
    assert (f[..., 2] <= 2).all()                    # still travelling south at nearly full length

def test_all_land_cell_encodes_as_empty():
    h = np.full((721, 1440), np.nan, np.float32)
    f = wave_frame(h, h, h, MODELS["ncep_gfswave025"])
    assert (f[..., 0] == 0).all() and (f[..., 1] == 128).all() and (f[..., 2] == 128).all()

def test_wave_peak_snaps_to_globe_cell():
    h = np.zeros((721, 1440), np.float32); h[537, 156] = 13.88      # 44.25 N, 141.0 W
    assert wave_peak(h, MODELS["ncep_gfswave025"]) == [13.9, 44.28, -140.92]
```

- [ ] **Step 2: Run** — expected: FAIL, module not found.
- [ ] **Step 3: Implement `pipeline/waves.py`.**
- [ ] **Step 4: Run the tests** — expected: 5 passed.
- [ ] **Step 5: Commit** `feat: wave frames, land fill and peaks`.

### Task 7: Run builder, manifest and command line

**Files:**
- Create: `pipeline/build.py`, `pipeline/__main__.py`, `tests/test_build.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `build_waves(run: datetime, cache_dir: Path, out_dir: Path, source: OpenMeteoRun | None = None) -> Path` — returns `out_dir/<YYYYMMDDHH>/`
  - Command: `python -m pipeline build --run 2026111306 --cache <dir> --out <dir>`; exit code 0 on success, 2 with a one-line message on `RunIncomplete`

Behaviour:
1. Before writing anything, call `source.meta()` and check all 57 frame times are in `valid_times`; else raise `RunIncomplete`.
2. Build into `out_dir/<run>.tmp/`: `globe-w0.webp … globe-w6.webp`, then `globe.json`; finally rename the folder to `out_dir/<run>/` (replace an existing one).
3. `globe.json`: `GLOBE.manifest_fields()` plus `"run": "2026-11-13T06:00Z"`, `"every": 3, "hours": 168, "frames": 57, "cols": 4, "chunks": [8,8,8,8,8,8,9]`, `"waves": true`, `"sources": {"wave": "<run time>"}`, `"peaks": {"wave": [...169 entries...]}` where entry `h` is `wave_peak` of frame `h // 3`. Compact JSON separators.
4. Process one frame at a time; hold at most one chunk of frames in memory.

- [ ] **Step 1: Write the failing tests** using a fake source object with `.source_grid`, `.meta()` and `.field()` that returns constant grids (height 2 + 0.1·frame index)

```python
def test_build_writes_seven_sprites_and_manifest(tmp_path): ...
    # 7 files globe-w{0..6}.webp; sizes (3072,768) x6 and (3072,1152)
    # manifest: frames == 57, chunks == [8,8,8,8,8,8,9], w == 768, north == 89.7364, sources == {"wave": "2026-11-13T06:00Z"}
    # len(peaks["wave"]) == 169; entries 0,1,2 equal; entry 3 differs from entry 2; entry 168 equals wave_peak of frame 56
    # no ".tmp" folder remains

def test_incomplete_run_writes_nothing(tmp_path): ...
    # fake meta lacks the last valid time -> RunIncomplete; out_dir is empty

def test_cli_exit_codes(tmp_path, monkeypatch): ...
    # main(["build", "--run", "2026111306", ...]) returns 2 and prints the RunIncomplete message when the source raises
```

- [ ] **Step 2: Run** — expected: FAIL, module not found.
- [ ] **Step 3: Implement `pipeline/build.py` and `pipeline/__main__.py`** (argparse; `main(argv) -> int`).
- [ ] **Step 4: Run the whole suite** `python -m pytest -v` — expected: all pass.
- [ ] **Step 5: Commit** `feat: wave run builder, manifest and CLI`.

### Task 8: Reference run test

**Files:**
- Create: `tests/test_reference_run.py`

**Interfaces:**
- Consumes: `build_waves`, `unpack_frame`, `decode_wave_height`.
- Inputs on disk (local only): `reference/openmeteo-inputs/2026111306/` (cache dir) and `reference/thetidechart-capture/site/wx__2026111306__globe-w0.webp`, `wx__2026111306__globe.json`.

- [ ] **Step 1: Confirm the inputs are complete.** `reference/openmeteo-inputs/2026111306/ncep_gfswave025/` must hold `meta.json` and 57 `.om` files (06:00 on 13 Nov to 06:00 on 20 Nov, every 3 h). If any are missing, run `python tools/save_reference_inputs.py` first (the bucket drops this run after 2026-11-19).

- [ ] **Step 2: Write the test**, marked `@pytest.mark.reference` and skipped with a clear reason when either input path is absent. Build the run once per module into `tmp_path_factory`.

```python
def test_chunk0_height_matches_reference(built, ref_sprite, sea_mask):
    for j in range(8):
        ours, theirs = unpack_frame(built_w0, j)[..., 0], unpack_frame(ref_sprite, j)[..., 0]
        assert (ours == theirs)[sea_mask].mean() >= 0.99
        assert np.abs(ours.astype(int) - theirs)[sea_mask].mean() <= 0.1

def test_chunk0_vectors_match_reference(built, ref_sprite, sea_mask):
    for j in range(8):
        for c in (1, 2):
            d = np.abs(unpack_frame(built_w0, j)[..., c].astype(int) - unpack_frame(ref_sprite, j)[..., c])
            assert d[sea_mask].mean() <= 1.0

def test_peaks_match_reference(built_manifest, ref_manifest):
    for h in range(169):
        (v, la, lo), (rv, rla, rlo) = built_manifest["peaks"]["wave"][h], ref_manifest["peaks"]["wave"][h]
        assert abs(v - rv) <= 0.1 and abs(la - rla) <= 1.0 and abs((lo - rlo + 180) % 360 - 180) <= 1.0

def test_manifest_grid_fields_identical(built_manifest, ref_manifest):
    for k in ("w", "h", "north", "west", "dlon", "dlat", "every", "hours", "frames", "cols", "chunks"):
        assert built_manifest[k] == ref_manifest[k]
    assert built_manifest["sources"]["wave"] == ref_manifest["sources"]["wave"]
```

`sea_mask` = globe cells whose four native neighbours in the hour-0 `wave_height` grid are all valid (strictly open sea, away from the coast fill).

- [ ] **Step 3: Run** `python -m pytest -m reference -v` — expected: 4 passed. If the vector or peak thresholds fail, report the measured numbers and stop; do not loosen thresholds without the owner's agreement.
- [ ] **Step 4: Run the full suite** `python -m pytest -v` — expected: all pass (reference tests included locally).
- [ ] **Step 5: Record the measured figures** (exact-match percentage per frame, mean vector difference, worst peak difference) in a short "Phase 1 results" section appended to the spec's section 9, then commit `test: reference run comparison for wave sprites`.
