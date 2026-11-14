# Phase 7: Station Catalogue, Search and Page Hosting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the station catalogue (NOAA CO-OPS gauges plus GeoNames coastal places) as static files, search it in the browser, build one page per station, and host every page on R2 with clean URLs.

**Architecture:** A Python command turns the NOAA tide-prediction station list, GeoNames `cities500` and the Natural Earth coastline into `stations.json` (full records), `search.json` (compact rows for the browser) and `countries.json` (counts for later browse pages). The web build reads `stations.json` and emits one page per station as `path.html`; a publish command uploads the built site to the bucket root with the `.html` dropped from page keys, so `/us/new-york/new-york-city` works on `r2.dev` with no routing rule, and uploads only files whose MD5 changed.

**Tech Stack:** Python 3.14 + numpy (no new dependency), Astro 7 + TypeScript, Vitest, Playwright, boto3 (`[publish]`).

**Spec:** `docs/superpowers/specs/2026-11-14-same-sources-data-design.md` (sections 4, 6 "Search, nearest and map markers", 7, 8 "Catalogue selection", 10 step 7). Record schema: `docs/wave-map-findings-and-plan.md` section 10.

## Global Constraints

- Sources: NOAA CO-OPS `mdapi/prod/webapi/stations.json?type=tidepredictions` (public domain) and GeoNames dumps `cities500.zip`, `admin1CodesASCII.txt`, `admin2Codes.txt`, `countryInfo.txt` (CC BY 4.0, credited on the pages). Nothing from thetidechart.com.
- Catalogue selection is our own rule (spec §8): every NOAA tide-prediction station, plus GeoNames populated places within `COAST_KM = 4.5` of the Natural Earth 50m coastline, deduplicated (a place within 0.5 km of a kept place with a larger population is dropped). Target near the reference: 24,631 records, 190 countries, United States 4,111.
- Record fields (findings §10): `id, slug, name, country_code, region_name, region_slug, county, island, latitude, longitude, timezone, type ("place" | "gauge"), has_tides, has_current_station, reference_station {slug, name, path} | null, timing_offset_minutes, path`. Ids are strings: `n<NOAA id>` for gauges, `g<GeoNames id>` for places.
- `path` = `{country_code lower}/{region_slug}/{slug}`, unique across the catalogue; slugs are ASCII `[a-z0-9-]`.
- Bucket layout: pages at the root (`us/new-york/new-york-city`, `weather-map`, `index.html`), `catalogue/*.json`, plus the existing `wx/` and `assets/globe/`. The site publisher never touches keys under `wx/`, `assets/` or `catalogue/`.
- Cache-Control: pages `public, max-age=3600`; `_astro/*` `public, max-age=31536000, immutable`; `catalogue/*` `public, max-age=86400`.
- Python file I/O always passes `encoding="utf-8"`. `reference/` and downloaded inputs are never committed.

## Review Focus

1. **Names that slug to nothing or collide** (non-Latin GeoNames names, two "Port Allen" in one state): every record gets a non-empty, unique path.
2. **Stations far from any GeoNames place** (mid-Pacific NOAA gauges): country, region and time zone still come out sensible, never empty.
3. **Search input with accents, case and punctuation** ("sao", "São Paulo", "st. john's"): finds the station; an empty or one-letter query shows nothing and never freezes the page.
4. **Republishing the site**: unchanged files are not re-uploaded; a page removed from the catalogue is deleted; nothing under `wx/`, `assets/` or `catalogue/` is deleted.
5. **Building without a catalogue** (CI, forks): the site still builds, with zero station pages.

---

### Task 1: Catalogue builder

**Files:**
- Create: `pipeline/catalogue.py`, `tests/test_catalogue.py`, `tests/fixtures/catalogue/` (tiny NOAA json, cities, admin1, admin2, countryInfo, coastline geojson)
- Modify: `pipeline/__main__.py` (subcommand `catalogue`), `tools/fetch_catalogue_inputs.py` (new: downloads the five inputs into a git-ignored folder), `.gitignore` (`catalogue-inputs/`, `catalogue-out/`)

**Interfaces:**
- Produces: `build_catalogue(noaa: Path, geonames: Path, coast: Path) -> list[dict]`; `write_catalogue(records, out: Path) -> None` writing `stations.json` (list of records), `search.json` (`{"v":1,"fields":["id","name","cc","region","lat","lon","type","path","rank"],"rows":[...]}`, lat/lon 4 dp, type 0 gauge / 1 place, rank = population-based 0–9, gauges 9) and `countries.json` (`[{cc, name, continent, count, regions:[{slug, name, count}]}]`); `slugify(name: str) -> str`; `coast_distance_km(lat, lon, coast_points) -> np.ndarray`.
- CLI: `python -m pipeline catalogue --inputs <dir> --coast <ne_50m_coastline.geojson> --out <dir>`.

- [ ] **Step 1: Write the failing tests** in `tests/test_catalogue.py`: `test_every_noaa_station_is_a_gauge`, `test_places_beyond_coast_km_are_dropped`, `test_close_smaller_place_is_deduplicated`, `test_gauge_takes_country_region_tz_from_nearest_place`, `test_gauge_far_from_places_still_has_tz_and_region` (Review Focus 2: falls back to the country of the nearest place at any distance and `Etc/GMT±N` from NOAA's `timezonecorr`), `test_place_within_5km_of_gauge_names_it_as_reference_station`, `test_paths_unique_and_ascii` (Review Focus 1: a CJK-only name slugs from GeoNames `asciiname`, then to `place-<id>`; duplicates get `-2`, `-3`), `test_search_rows_match_records`, `test_countries_counts_sum_to_total`.
- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_catalogue.py -q` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `pipeline/catalogue.py`. Coast distance: densify coastline segments every 0.005°, bin points into 0.25° cells, take the minimum great-circle distance over the 3×3 neighbouring cells (99 km when none). Region = GeoNames admin1 name (country name when admin1 is empty or unknown); county = admin2 name or null; island = null (no island source; ruling); `has_tides` true; `has_current_station` false; `timing_offset_minutes` null (offsets come in phase 8).
- [ ] **Step 4: Run** the tests — Expected: PASS. Then fetch real inputs and run the command; add `test_real_catalogue_near_reference_counts` (marker `reference`, skipped without `catalogue-inputs/`): total within ±15 % of 24,631, United States within ±25 % of 4,111, countries within ±15 % of 190, `search.json` gzip-compressed under 2 MB. Record the real counts in the ledger.
- [ ] **Step 5: Commit** `feat: station catalogue from NOAA CO-OPS and GeoNames coastal places`.

### Task 2: Browser search

**Files:**
- Create: `web/src/search/catalogue.ts`, `web/src/search/box.ts`, `web/src/components/SearchBox.astro`, `web/src/search/search.test.ts`, `web/tests/e2e/search.spec.ts`
- Modify: `web/src/pages/*.astro` globe pages and `RegionPage.astro` headers (add the box), `web/src/styles/globe.css`

**Interfaces:**
- Consumes: `search.json` from Task 1 at `${PUBLIC_CATALOGUE_BASE ?? "/catalogue"}/search.json`.
- Produces: `loadCatalogue(): Promise<Catalogue>`; `fold(s: string): string` (NFD, strip marks, lower-case, punctuation to spaces, collapse spaces); `search(c, q, limit = 8): Entry[]`; `nearest(c, lat, lon, n): (Entry & {km: number})[]`; `inBounds(c, west, south, east, north, limit): Entry[]` (handles west > east across ±180).

- [ ] **Step 1: Write failing vitest tests**: `fold("São Paulo") === "sao paulo"`, `fold("St. John's") === "st john s"`; ranking — exact name, then name prefix, then word prefix, then substring, ties by rank then name; queries shorter than 2 folded characters return `[]`; `nearest` orders by great-circle km; `inBounds` across the antimeridian.
- [ ] **Step 2: Run** `npx vitest run src/search` — Expected: FAIL.
- [ ] **Step 3: Implement**; precompute folded names once at load. `box.ts`: combobox per WAI-ARIA (input `role="combobox"`, listbox, arrow keys, Enter opens, Escape closes), loads the catalogue on first focus, debounced 80 ms; each result links to `/${path}` and shows "region, country".
- [ ] **Step 4: Run** vitest, then the e2e spec (skips without `web/public/catalogue/search.json`): typing "new york" lists a result whose link ends in `/new-york-city`; arrow-down + Enter navigates; Escape closes; 320 px width has no horizontal scroll.
- [ ] **Step 5: Commit** `feat: station search in the header, searched in the browser`.

### Task 3: One page per station

**Files:**
- Create: `web/src/pages/[cc]/[region]/[station].astro`, `web/src/stations/catalogue.ts` (build-time loader), `web/src/stations/catalogue.test.ts`, `web/tests/e2e/station.spec.ts`
- Modify: `web/astro.config.mjs` (`build.format: "file"`)

**Interfaces:**
- Consumes: `stations.json` from `process.env.CATALOGUE_FILE ?? "public/catalogue/stations.json"`; `REGIONS` from `web/src/region/regions.ts` with bounds (add `west, east, south, north` to `RegionInfo` and its Python sync test).
- Produces: `loadStations(file?: string): StationRecord[]` returning `[]` when the file is missing (Review Focus 5); `nearbyStations(all, s, n = 8)`; `regionFor(s): RegionInfo | null` (first region whose bounds contain the station).

- [ ] **Step 1: Failing vitest tests** for `loadStations` (missing file → `[]`), `nearbyStations` (excludes itself, ordered by km), `regionFor`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** the page: title "{name} tide times and weather · 3Dweather"; h1 "{name}"; breadcrumb country / region; local time zone; type line ("NOAA tide gauge {id}" or "Coastal place"; "Tides from {reference station}" when set); links to the globe deep link at the station and to the regional map when `regionFor` finds one; "Nearby" list of 8; credits including GeoNames (CC BY 4.0) and NOAA CO-OPS. Tide and weather sections are phase 9; the page says the tide table is coming.
- [ ] **Step 4: Verify**: vitest PASS; `npm run build` with the real catalogue — record page count and build time in the ledger; e2e `station.spec.ts`: the New York City page has its h1, a nearby link that works, and the globe link; existing e2e suites still pass under `format: "file"`.
- [ ] **Step 5: Commit** `feat: a page for every station`.

### Task 4: Site publishing on R2

**Files:**
- Create: `pipeline/site.py`, `tests/test_site.py`, `.github/workflows/site.yml`
- Modify: `pipeline/publish.py` (`Store.list_etags(prefix) -> dict[str, str]` on `DirStore` (MD5 of the stored file) and `S3Store` (ETag without quotes)), `pipeline/__main__.py` (`publish-site`, `upload-catalogue`), `.github/workflows/static.yml` (catalogue step), `tests/test_workflows.py`, `docs/deploy.md`, README, spec §9 phase 7 results

**Interfaces:**
- Produces: `site_key(rel: str) -> str` (`a/b.html` → `a/b`; `index.html` and `404.html` keep their names; other files unchanged); `site_cache_control(key) -> str`; `publish_site(store, dist: Path) -> dict` returning `{"uploaded": n, "unchanged": n, "deleted": n}`. Keeps `site-manifest.json` (keys it published) at the root and deletes only keys in the old manifest that are gone from the new build, never under `wx/`, `assets/`, `catalogue/` (Review Focus 4).

- [ ] **Step 1: Failing tests**: `test_site_key_drops_html`, `test_pages_served_as_html` (content type `text/html; charset=utf-8` for extensionless page keys), `test_cache_controls`, `test_second_publish_uploads_nothing`, `test_changed_page_uploaded_alone`, `test_removed_page_deleted_and_wx_untouched`, workflow tests (site.yml builds with `CATALOGUE_FILE` downloaded from the bucket and runs `publish-site`; static.yml builds and uploads the catalogue).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement**. `site.yml`: on push to `main` and `workflow_dispatch`; skips with a notice without secrets; downloads `catalogue/stations.json` from `vars.PUBLIC_BUCKET_URL`, builds with `PUBLIC_WX_BASE=/wx`, `PUBLIC_ASSET_BASE=/assets/globe`, `PUBLIC_CATALOGUE_BASE=/catalogue`, runs `python -m pipeline publish-site web/dist`. Docs: R2 serves the root page only through a custom domain rule (`/` → `/index.html`), noted for launch.
- [ ] **Step 4: Run** the full pytest suite — Expected: PASS.
- [ ] **Step 5: Commit** `feat: publish the built site to R2 with clean URLs, changed files only`.
