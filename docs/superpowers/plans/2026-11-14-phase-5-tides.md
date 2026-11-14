# Phase 5: Tide atlas and tide layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a global tide atlas texture built from EOT20, an openly licensed stand-in until FES2022 is licensed. A `/tide-map` globe page draws the tide height for any moment of the forecast timeline, computed in the browser from 8 constituents.

**Architecture:**
- `pipeline/tide_astro.py` computes monthly nodal factors f and V+u for 2026–2035, using Schureman's formulas.
- `pipeline/tide_atlas.py` reads the 8 EOT20 ocean-tide constituents straight from the downloaded zip. It averages each constituent over 4×4 blocks of 1/8° cells to a 0.5° grid, working on the complex value A·e^{iG}. It then writes:
  - `tide.png`: 720×2160 RGB, 6 tiles, 16 signed channels plus a sea mask;
  - `tide.json`: grid, constituents, `amax`, speeds and the monthly table.
- The browser evaluates h = Σ f·A·cos(V+u−G) per pixel in the shader, and for the readout on the CPU.

**Tech Stack:** Python with h5py 3.16.0 (EOT20 is netCDF4/HDF5); TypeScript and WebGL1 as in phase 3b.

**Spec:** `docs/superpowers/specs/2026-11-14-same-sources-data-design.md`:
- §4: FES2022, with EOT20 as the stand-in;
- §5: the static tide atlas, 8 constituents at 0.5° with monthly nodal factors;
- §9: the tide atlas test compares `amax`;
- §10, phase 5.

## Global Constraints

- Constituents, in order: m2, s2, n2, k2, k1, o1, p1, q1. Speeds are in rad/h. The monthly table runs for 120 months from 2026-01-01T00Z, as 16 numbers per month: (f, V+u) for each constituent.
- Grid: 720×360, west −179.75, north 89.75, 0.5° spacing (cell centres).
- Encoding:
  - Channel 2k holds X_k = A·cos G and channel 2k+1 holds Y_k = A·sin G, both in metres. Bytes are `round(v/amax_k·127)+128`.
  - Tiles are stacked vertically, 3 channels per tile.
  - Channel 16 (tile 5, G) is the sea mask: 255 for sea, 0 for land or no data.
  - Channel 17 is spare and always 0.
- Credit: "Tides: EOT20 (Hart-Davis et al., DGFI-TUM), CC BY 4.0". It must be clear that this is not FES2022.
- The tide layer is sea-only and diverging: low water in blue, high water in red, over ±3 m.

## Review Focus

1. **Phase sign convention.** The atlas G is a Greenwich phase lag, so the tide is cos(V+u−G), not cos(V+u+G). A pinned test at a point with known constants covers this in Task 3.
2. **Month boundaries.** The phase at hour 0 of a month from the table must equal the previous month's value advanced by its speed, to within 1°. Covered in Task 3.
3. **Times outside 2026–2035.** Clamp to the nearest month rather than crashing or showing NaN. Covered in Task 3.
4. **Coastal cells.** A cell that is partly sea averages only its sea sub-cells, and a cell with no sea sub-cells gets mask 0. Covered in Task 2.
5. **Antimeridian.** Block averaging must not blend across −180/180, and the shader must wrap x. Covered in Task 2 and by the e2e test in Task 4.

---

### Task 1: Astronomy

**Status:** done (commit 489b98f).

`nodal(t) -> {name: (f, V+u rad)}`, `month_starts`, `CONSTITUENTS`, `SPEEDS_RAD_PER_HOUR`. All three months tested match the reference's published monthly values: f within 0.002 and phase within 0.5°.

### Task 2: Atlas builder

**Files:**
- Create `pipeline/tide_atlas.py` and `tests/test_tide_atlas.py`.
- Modify `pipeline/__main__.py` (subcommand `tide-atlas --eot20 ZIP_OR_DIR --out DIR`) and `pyproject.toml` (extra `tides = ["h5py==3.16.0"]`).

**Produces:**
- `read_constituent(source, name) -> (lat, lon, amp_m, phase_deg)`
- `to_atlas_grid(lat, lon, amp, phase) -> (X, Y, sea)`
- `encode_atlas(fields) -> (png RGB array 2160×720×3, amax)`
- `build_tide_atlas(source, out_dir, start=2026-01, months=120)`

**Tests:**
- A synthetic HDF5 file on a 1/8° grid with constant A and G gives exact X and Y after regridding.
- In a coast cell where half the sub-cells are NaN, only the sea half is averaged.
- A cell that is all NaN gets mask 0 and bytes 128.
- The encode/decode round trip is within one byte.
- The `tide.json` keys and the monthly table length are right.
- A reference test (needs `eot20/eot20.zip` and the capture): our `amax` per constituent against the reference's, within a measured bound.

### Task 3: Tide maths in the browser

**Files:** create `web/src/globe/tide.ts` and `web/src/globe/tide.test.ts`.

**Produces:**
- `TideAtlas` type (the JSON plus the decoded pixels)
- `phasesAt(atlas, t: Date) -> {c: number[], s: number[]}`, where c_k = amax_k·f_k·cos φ_k and s_k = amax_k·f_k·sin φ_k
- `tideAt(atlas, lat, lon, t) -> {heightM, rising} | null` (null over land)

**Tests:**
- A synthetic atlas with a single M2 term: h = A·cos(φ−G) at a few times, with the sign pinned.
- Month boundary continuity.
- Times outside the table are clamped.
- Bilinear sampling wraps at the antimeridian.
- "Rising" means h(t + 10 min) > h(t).

### Task 4: Tide layer page

**Files:**
- Modify `web/src/globe/layers.ts` (layer `tide`, path `/tide-map`, shade kind `tide`, flow optional), `renderer.ts` (the tide texture on unit 4 and uniforms `uTideC[8]`, `uTideS[8]`, `uTileH`), `globe.ts` (the tide path in `applyHour`, the readout and "Highest tide now"), `probe.ts` ("Tide +1.2 m, rising" or "Land — no tide data").
- Create `web/src/pages/tide-map.astro`.
- Modify `web/tests/e2e/layers.spec.ts`.
- `static.yml` builds and uploads the atlas.

**Tests:**
- Unit: the readout lines and the layer registry entry.
- e2e:
  - `/tide-map` loads with the legend "Tide height", and its colour changes between hour 0 and hour 3 at a strong-tide point (Bay of Fundy, 45.0, −65.5, zoom 4);
  - the readout reads a height in m and in ft;
  - the tab switch works to and from tide;
  - no seam at the antimeridian.
- The dev atlas lives in `web/public/assets/globe/`, which is not committed.
