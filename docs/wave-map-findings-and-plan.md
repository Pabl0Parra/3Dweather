# Wave map: reverse-engineering findings and build plan

> **Superseded in part (2026-11-14).** Sections 8, 9 and 11-16 no longer apply:
> the owner dropped own-buoy data, FastAPI and MySQL. The current design is
> `docs/superpowers/specs/2026-11-14-same-sources-data-design.md`. Sections 1-7
> and 10 remain valid as findings about the reference site.

Target studied: `https://www.thetidechart.com/wave-map#44.5,9.5,2.7` on 2026-11-13.
Method: REA headless Chrome capture (network, bodies, DOM, screenshots) plus direct
fetch of the public data files the page requests. Raw capture is in
`reference/thetidechart-capture/` (`site/` = files, `screenshots/` = renders).

Everything under "Observed" was read from shipped files or network traffic.
"Inferred" is a conclusion drawn from them. "Unknown" was not visible from outside.

---

## 1. The key finding

**There is no map library and no data API.** The page is a hand-written WebGL globe
(orthographic projection, one full-screen fragment shader) that reads the forecast
from **pre-rendered static image sprites** on a CDN. Every value shown — colours,
moving lines, the tap readout, "biggest waves" — is computed in the browser from
those images. Tapping the sea makes **zero** network requests.

That means the "backend" for the map is a batch job that writes files, not a
request-time service.

## 2. Their stack

| Part | What it is | Evidence |
|---|---|---|
| Pages | Server-rendered PHP (Laravel/Blade) | leaked `<?php ... context() ...` in JSON-LD; comment names `WeatherMapController::globe` |
| Data pipeline | Python scripts, batch | comments name `tide-service/scripts/weather_map_frames.py`, `globe_static.py` |
| Front end | Plain ES5 JS, no framework, no bundler, unminified | `core.js`, `weather-core.js`, `weather-sky.js`, `weather-globe.js` loaded with `<script defer>` |
| Hosting | Cloudflare CDN in front | `server: cloudflare`, `cf-cache-status: HIT` |
| Data source | Open-Meteo (NOAA GFS + GFS-Wave, ECMWF IFS, Mercator/Copernicus), FES2022 tides | on-page attribution, `globe.json.sources` |
| Base map art | Natural Earth II, NASA Black Marble, Yale Bright Star Catalogue | `terrain.json.source`, `sky.json.source` |

Unknown: their database, how the pipeline is scheduled, how Open-Meteo data is
pulled in bulk (probably Open-Meteo's open-data bucket, not the per-point API).

## 3. Network sequence on load

1. `GET /wave-map` — HTML, 85 KB, `s-maxage=600`.
2. `site.css` (360 KB), `core.js`, `account.js`, `weather-core.js`, `weather-sky.js`, `weather-globe.js`, 2 fonts.
3. Static globe assets (`max-age=604800`):
   `land-night.png` (2048×1024, R = land mask, G = city lights), `coast.json` (712 KB),
   `rivers.json` (480 KB, ranked), `sky.json` (1,630 stars + 17 constellations),
   `terrain-4096.webp` (4096×2048; 2048 on phones), `terrain.json` (tile index for z3/z4 512 px tiles at `terrain/{z}/{x}-{y}.webp`).
4. `GET /wx/latest.json` (`max-age=60`) → `{"run","dir","regions","built"}`.
5. `GET /wx/{dir}/globe.json` (`max-age=2592000`, immutable per run).
6. `GET /wx/{dir}/globe-a0.webp`, `globe-b0.webp` (base: wind/rain/cloud), then `globe-w0.webp` because the layer is waves. Next chunk (`a1/b1/w1`) follows as playback approaches it.

Run directory name = run time as `YYYYMMDDHH`. A run built ~5.5 h after its nominal time (run 06:00Z, built 11:30Z).

## 4. Data format (the part to copy in spirit)

### `globe.json`

```json
{"run":"2026-11-13T06:00Z","w":768,"h":384,"north":89.7364,"west":-179.82422,
 "dlon":0.46875,"dlat":0.468597,"every":3,"hours":168,"frames":57,"cols":4,
 "chunks":[8,8,8,8,8,8,9],"pressure":true,"gust":true,"gustHours":84,"waves":true,
 "currents":true,"currentEvery":24,"currentFrames":8,"storms":true,
 "sources":{"ecmwf":"...","wave":"...","cur":"...","sst":"..."},
 "peaks":{"wave":[[13.9,44.28,-140.92], ...169 hourly [value,lat,lon]], "wind":[...], ...}}
```

- Grid: 768×384 equirectangular, ~0.47° (~50 km). Cell (x,y) → lon = west + x·dlon, lat = north − y·dlat.
- Time: a frame every 3 h for 168 h (57 frames), grouped into 7 day-chunks.
- `peaks` = precomputed hourly global maxima, used by the "next seven days" text.

### Sprites

Each chunk file is one **lossless WebP, 3072×768** = 4 columns × 2 rows of 768×384
frames (frame j at column `j % cols`, row `floor(j / cols)`). ~1.7–2.7 MB each.

| File | R | G | B |
|---|---|---|---|
| `globe-a{i}` | wind u | wind v | rain |
| `globe-b{i}` | cloud | pressure | gust |
| `globe-t{i}` | air temperature | – | – |
| `globe-w{i}` | **wave height** | **wave travel x** | **wave travel y** |
| `globe-s{i}` | thunderstorm index | – | – |
| `globe-c` (single file, 8 daily frames) | current u | current v | sea temperature |

Byte decodings (verified against a real frame: max byte 237 → 13.8 m at 44.75N 141.39W; published peak 13.9 m at 44.28N 140.92W):

| Quantity | Decode |
|---|---|
| Wave height, m | `(b/255)² × 16` |
| Wave vector | `(b−128)/127` per axis; **length × 25 = period in s**; direction = where the waves travel |
| Wind u/v, m/s | `(b−128) × 50/127` |
| Gust, m/s | `b/255 × 60` |
| Rain, mm/h | `(b/255)² × 64` |
| Air temp, °C | `b/255 × 110 − 60` |
| Sea temp, °C | `b/255 × 36 − 2` |
| Current, m/s | `(b−128)/127 × 2.5` |
| Pressure, hPa | `940 + (b−1)/254 × 120` (0 = none) |

Land cells in the wave sprite are filled (not zero), so the sea mask clips cleanly at coasts.

## 5. Rendering

Four stacked canvases inside one container:

1. `sky` (2D) — stars at the real sidereal time.
2. `gl` (WebGL1) — one triangle covering the canvas. The fragment shader inverse-projects each pixel to lat/lon, then composes: sea/land colour → terrain texture → data layer through a 256×1 colour-ramp texture → relief shading → city lights on the night side → limb atmosphere. Two frames are bound and blended (`uMix`) for smooth time.
3. `top` (2D) — graticule every 30°, coastline, rivers (zoom ≥ 1.6), 56 city labels; redrawn only when the view moves.
4. `flow` (2D) — particle trails, probe marker, storm rings, pin.

Projection: orthographic. `R = zoom × 0.45 × min(W−16, H−16)`; zoom clamped 0.75–16; lat0 clamped ±85.

Wave colour ramp (m → RGBA): 0 `20,45,90,.35` · 0.5 `30,90,160,.6` · 1.5 `35,150,185,.75` · 2.5 `70,190,140,.82` · 4 `225,210,70,.86` · 6 `240,140,40,.9` · 9 `215,50,50,.93` · 12 `150,40,160,.95` · 16 `240,225,255,.97`. Legend scale is `sqrt(h/12)` with ticks 1, 3, 6, 9, 12 m.

Particles ("the lines run the way the waves travel"):
- Count ≈ visible disk area / 95, clamped 400–5000 (2400 below 720 px wide).
- Each keeps 14 past positions as lon/lat so trails stay glued to the ground while the globe turns.
- Step: sample the wave vector bilinearly (blended in time), speed `sp^0.65`, east-west step divided by cos(lat). Wave vectors get ×14 gain to move at a wind-like pace.
- Respawn after 40–120 steps, off-screen, past ±88°, or on land (512×256 land mask).
- Drawn as white 1.1 px lines, alpha fading with age (0.55 max for waves).
- On touch devices coast, rivers and particles are drawn in GL instead of 2D for speed; busy canvases capped at DPR 1.25.

Memory: only the chunk in view plus neighbours stay loaded; frames are unpacked one per animation frame to avoid stalls. Failed files retry at 2, 4, 8, 16 s.

## 6. Features to reproduce

| Feature | Behaviour |
|---|---|
| Deep link | `#lat,lon,zoom` opens a place; the hash is rewritten 600 ms after the view settles |
| Layer switch | Rain / Wind / Temperature / Waves / Currents / Tide — real URLs, switched in place with `history.replaceState` and a title swap |
| Timeline | Slider 0–168 h step 0.05, day ticks at local midnight, "now" marker, play/pause, speed 1× / 2× / ½× (1× = 1.5 forecast hours per second), loops back to now |
| Time label | Local date/time + "in 12 h" / "in 3 days" / "· less certain" past 120 h |
| Tap readout | Wave height, period, direction from; wind + gusts; rain; cloud; coordinates |
| "Biggest waves" | Scans the current frame for the highest sea cell and flies there (1.4 s eased, zoom 3.2) |
| Controls | Zoom ±, whole-Earth/auto-spin toggle (4°/s), my location, day/night, sound, share, full screen (F) |
| Gestures | Wheel scrolls the page until the map is clicked ("cooperative gestures"); drag with inertia; pinch; double-click zoom; arrow keys, + and − |
| Units | m/ft, kn/km/h/m/s/mph, °C/°F from a header settings menu, stored in localStorage |
| Courtesy | Pauses off-screen (IntersectionObserver), honours reduced-motion and Save-Data |
| SEO block | "World in the next seven days" stats from `peaks`, FAQ with JSON-LD, breadcrumb |
| Extras | Ambient weather sound (WebAudio), lightning flashes, isobars, regional flat maps — skip in v1 |

## 7. What not to copy

Their JS, CSS, copy text, logo and audio are their own work, and `robots.txt`
declares `ai-train=no, use=reference`. Use the capture as a **reference for
behaviour and formats only**; write the code fresh. The underlying data and base
art are open and can be sourced directly: NOAA GFS-Wave (public domain),
Natural Earth (public domain), NASA Black Marble (public domain), Open-Meteo and
ECMWF open data (CC BY 4.0, attribution required).

---

## 8. Proposed architecture (Astro + TypeScript, FastAPI, MySQL)

```
NOAA GFS-Wave GRIB2 ─┐
(v2: your MySQL DB) ─┼─► Python pipeline ─► /wx/{run}/globe.json + globe-w{i}.webp ─► CDN/static
                     │         │
                     │         └─► MySQL: runs, peaks, spots
                     │
Astro (TS) pages ◄───┴── FastAPI (OpenAPI): /runs/latest, /peaks, /point, /spots
   └─ globe island (WebGL, TS) reads sprites directly from static storage
```

Keeping the static-sprite design is the main recommendation: it is why their map
is fast and cheap. FastAPI handles metadata and anything that needs a query; the
heavy pixels never pass through it.

### Components

**Pipeline (`pipeline/`, Python)** — the only place that knows where data comes from.
- `sources/gfs_wave.py`: download significant height, peak period, mean direction (0.25° global, 3-hourly to 168 h) from NOAA open data; read with `xarray` + `cfgrib`.
- `sources/base.py`: a small `WaveSource` interface returning `(height, period, direction)` grids per valid time. **v2 adds `sources/mysql.py` behind the same interface**, so nothing downstream changes.
- `encode.py`: regrid to 768×384, fill land, pack bytes as in section 4, write lossless WebP sprites + `globe.json`, compute `peaks`.
- `publish.py`: write to `data/wx/{run}/`, then update `latest.json` last (atomic switch), prune old runs.
- Run on a schedule (cron/systemd timer or APScheduler) every 6 h.

**API (`api/`, FastAPI)** — documented at `/docs` (OpenAPI).
- `GET /api/runs/latest` → latest run pointer.
- `GET /api/runs/{run}/peaks?layer=waves` → hourly maxima for the stats block.
- `GET /api/point?lat&lon&hours` → time series at a point (decoded from the sprites in v1; from your DB in v2).
- `GET /api/spots?bbox` → named places/stations, once your DB is in.
- Serves `/wx` static in dev; nginx/CDN in production.

**MySQL** — v1 schema kept small: `forecast_runs(id, run_time, built_at, status, source)`, `forecast_peaks(run_id, layer, hour, value, lat, lon)`. v2 adds whatever maps your existing tables onto `WaveSource`.

**Web (`web/`, Astro + TS)**
- `src/pages/wave-map.astro` (static shell, SEO text, FAQ, stats fetched at build or on request).
- `src/globe/` as a framework-free TS module mounted as a client island:
  `projection.ts`, `shader.ts`, `frames.ts` (manifest, chunk window, decode), `particles.ts`, `overlay.ts` (coast, cities, graticule), `probe.ts`, `timeline.ts`, `gestures.ts`, `units.ts`, `ramps.ts`.
- `scripts/build-static.ts` (or Python): build coast/land-mask/terrain assets from Natural Earth and Black Marble.

### Build order

1. **Static globe**: projection, land mask, coastline, drag/zoom/hash. No data yet.
2. **Pipeline v0**: one GFS-Wave run → sprites + `globe.json`; verify by decoding a known cell.
3. **Wave layer**: ramp texture, two-frame blend, timeline, play/pause.
4. **Particles** following the wave vectors.
5. **Probe + "biggest waves" + units + legend.**
6. **FastAPI + MySQL**: runs, peaks, point endpoint, OpenAPI; scheduled pipeline.
7. **Polish**: terrain texture, night side, full screen, mobile GL paths, reduced-motion, share.
8. **v2**: `sources/mysql.py` for your wave/wind data; add the wind layer (same sprite format, `a` channels).

---

## 9. Decisions from the owner (2026-11-13)

| Question | Answer | Consequence |
|---|---|---|
| What is in the database? | Full weather-station files with many variables, from the company's own buoys around the world | Point observations, not a grid. See section 11 |
| v1 scope of layers | Everything | All six globe layers (rain, wind, temperature, waves, currents, tide) and the flat regional maps |
| Hosting | "single page" — read as a single server; **to confirm** | nginx serves pages, API and `/wx` files from one machine |
| Surrounding site | In scope | Station pages, browse pages, search, accounts, alerts, guides, embed widget (section 10) |

## 10. The rest of the site (second capture, `reference/thetidechart-capture/pages/`)

### Page types

| URL pattern | What it is | Scripts |
|---|---|---|
| `/` | Hero + station search, "your stations", "tides near you", popular stations, mini live globe, world map, continents tabs | `home.js`, `charts.js`, globe |
| `/{cc}` | Country: region cards with filter/sort, popular spots, link to country weather map | `stations.js` |
| `/{cc}/{region}` | Region: popular spots, all locations grouped by island/mainland, filter | `stations.js` |
| `/{cc}/{region}/{station}` | **Station page** (574 KB HTML, the heart of the site) | `station.js`, `charts.js`, `alert-panel.js`, globe |
| `/stations` | All locations by continent + Leaflet/OSM finder map with clustering | `stations.js`, Leaflet, markercluster |
| `/weather-map`, `/wind-map`, `/temperature-map`, `/wave-map`, `/ocean-currents-map`, `/tide-map` | The globe, one URL per layer | globe |
| `/weather-map/{region}` (12 regions) | Flat regional map, 72 h hourly, 2× detail | `weather-map.js` |
| `/guides`, `/what-is-a-tide`, … | Static articles | – |
| `/embed` | Embeddable tide widget builder (iframe) | – |
| `/login`, `/register` | Auth forms with Cloudflare Turnstile | `auth.js` |
| `/about`, `/contact`, `/privacy`, `/terms` | Static | – |
| `/sitemap.xml` | Index → pages, geo, stations sitemaps | – |

### Station page sections, in order

Now card (today, next turn, countdown) · "Is today good for…" tabs (fishing,
snorkelling, boating, beach, surf, photography) · date chips and 7 day-cards ·
tide chart (range and unit switches) · next 7 days table · hour-by-hour · tidal
coefficient strip · weather & sea (2-hourly strip, barometer chart, UV, water
temperature, 7-day, air quality) · **globe in "station" mode, pinned on the
place** · waves chart · plan ahead (best days, bite windows) · moon/sun/daylight ·
fishing solunar timeline · month tide table (CSV export) · local notes · nearby
(Leaflet map + list) · FAQ with JSON-LD.

How it is served (from `station.js` comments): the HTML is **one cached document
for all visitors, served for hours**. It embeds a JSON blob (`<script
type="application/json" id="tc-data">`) with 30 days of data, and the script
computes everything that depends on "now" in the station's own time zone.
`tc-data` keys: `tz, tzLabel, hasTides, stationName, lat, lon, today,
todayWindows[], nextTides[], sky{sunrise, sunset, moonrise, moonName, …},
days[30]{date, sunrise, sunset, coef, tides, moon, windows, curve}`.

### JSON endpoints observed

| Endpoint | Purpose | Shape |
|---|---|---|
| `GET /api/stations?q=` | Search (header box, home, finder) | Paginated: `current_page, data[], per_page: 20, total, …` |
| `GET /api/stations/nearest?lat&lon&limit` | Near me | `data[]` + `distance_km` |
| `GET /api/stations/in-bounds?bbox=` | Finder map markers per viewport | `data[]` (bbox required) |
| `GET /home/featured`, `/home/near-me` | Home page cards | not sampled |
| `/account/favorites/`, `/account/favorites/merge`, `/account/preferences` | Signed-in state; local favourites merge into the account on sign-in | not sampled (need a session) |
| `POST /account/alerts/request`, `/account/alerts` | Tide alert e-mails | not sampled |

Station record: `id, slug, name, country_code, region_name, region_slug, county,
island, latitude, longitude, timezone, type ("place" | "gauge"), has_tides,
has_current_station, reference_station{slug, name, path}, timing_offset_minutes,
path, url`.

Flat regional map files: `/wx/{dir}/{region}.json` (grid, focus box, tz, cities,
peaks), `{region}-a.webp` (u, v, rain; 8 columns), `{region}-b.webp` (cloud),
`/wx/land/{region}.json`. Four canvases, equirectangular, same ramps as the globe.

Not studied: signed-in account pages, alert e-mails, the embed iframe itself, the
native apps, `charts.js` and `station.js` internals (saved, 110 KB each).

## 11. What the buoy database changes

A globe layer needs a value at every one of ~295,000 grid cells. Buoys give
values at a few hundred or thousand points. Spreading buoy readings across whole
oceans would invent data, so the two sources get different jobs:

- **Forecast models stay the globe's background** (NOAA/ECMWF grids, as on the reference site).
- **Your buoys become the site's stations.** Where the reference site has tide gauges and places, Waves5 has buoys: each gets a station page driven by its own measured variables, appears as a marker on the globe and the finder map, and shows up in search and "nearest".
- **Observed vs forecast** is the feature the reference site cannot offer: on a buoy page, plot the buoy's measured waves and wind against the model forecast for that cell.

So the `WaveSource` interface in section 8 stays model-only, and v2 adds a
separate `stations` domain: MySQL tables for buoys and their observations, API
endpoints `/api/stations`, `/api/stations/{id}/observations`, and a markers
layer on the globe.

## 12. Revised build phases

1. **Globe core** — projection, land, coast, gestures, deep link.
2. **Pipeline** — all model fields → sprites and manifests (global + 12 regions).
3. **All globe layers** — waves, wind, rain/cloud, temperature, currents; timeline, particles, probe, hot spots, units.
4. **Tide layer + tide predictions** — harmonic synthesis from tidal constituents. Largest single risk: FES2022 needs an AVISO+ licence, and station tide tables need per-station constants.
5. **Flat regional maps.**
6. **API + MySQL** — stations, search, nearest, in-bounds, runs, peaks; OpenAPI.
7. **Site shell** — home, country/region/browse pages, finder map, guides, SEO (sitemaps, JSON-LD).
8. **Station page** — charts engine and all sections that apply to a buoy.
9. **Marine operations** — profiles, hourly go/marginal/no-go, weather windows (section 14).
10. **Accounts** — register/login, favourites, preferences, alerts.
11. **Embed widget.**
12. **v2** — CSV ingestion from the owner's server, buoy station pages, tides fitted from buoy records, observed-vs-forecast (section 15).

With ~10 stations, phase 7 shrinks: the country and region browse pages are replaced by one stations page.

## 13. Second round of decisions (2026-11-13)

| Topic | Answer | Consequence |
|---|---|---|
| Tides | Important | Phase 4 stays. Tide layer on the globe and tide predictions per station |
| Marine operations | Add a "good or not for offshore work" assessment | New feature, section 14. Replaces the consumer "is today good for…" tabs |
| Buoy data format | CSV, a timestamp column plus many variable columns | Ingestion job: CSV → MySQL, section 15 |
| Number of stations | About 10 | No country/region browse tree needed; one stations page with a map and a list |
| Access | Data sits behind the owner's own server | The pipeline pulls from that server; credentials stay in server-side config, never in the front end |

## 14. Marine operations workability (new, not on the reference site)

The question an offshore planner asks is "can I do this job, and when is the next
window long enough to finish it?" The answer comes from comparing forecast and
measured conditions against limits for a type of operation.

- **Operation profiles**: named sets of limits, stored in MySQL and editable. Each limit is a variable, a maximum (or minimum) and an optional direction sector. Typical variables: significant wave height, peak period, wind speed and gust at a stated height, current speed, visibility, and tide level or range for jobs that depend on water depth.
- **Status per hour**: go / marginal / no-go. Marginal = within a configurable margin of any limit (default 80–100 %). The status always names the variable that decides it.
- **Weather windows**: runs of consecutive "go" hours at least as long as the operation's required duration. Shown as a 7-day strip per profile, with the next usable window called out.
- **Where it appears**: on each station page (top card, replacing "Is today good for…"), as a column in the stations list, and as marker colour on the globe and stations map.
- **Observed check**: the current hour uses the buoy's latest measurement when it is fresh; the forecast hours use the model at the buoy's position. Once enough history exists, the forecast can be bias-corrected against the buoy.

The limits themselves must come from the owner's operations people. Shipping
invented defaults as if they were guidance would be unsafe; v1 ships with
clearly labelled example profiles that must be edited before use, and the page
states that the result is decision support, not a substitute for the vessel
master's or offshore manager's judgement.

API: `GET /api/operations/profiles`, `GET /api/stations/{id}/workability?profile=`,
`GET /api/stations/{id}/windows?profile=&min_hours=`.

## 15. Buoy data: CSV ingestion and tides

**Ingestion.** A scheduled Python job fetches each station's CSV from the owner's
server, parses it with a per-station column map (CSV column → canonical variable
+ unit), and upserts into MySQL keyed on `(station_id, time, variable)` so
re-reading a file never duplicates rows. Bad or out-of-range values are flagged,
not dropped. With ~10 stations the volume is small; a plain long table is fine.

Tables: `stations`, `station_variables` (column map and units),
`observations(station_id, time_utc, variable, value, qc_flag)`,
`operation_profiles`, `operation_limits`, plus `forecast_runs` and
`forecast_peaks` from section 8.

**Tides, two sources.**
- *At the buoys*: if the CSV has water level (or bottom pressure) over a long enough record — a month gives the main constituents, a year gives a good set — fit tidal constituents per station with harmonic analysis (`utide` in Python). That yields predictions from the owner's own measurements, with no third-party licence, and the residual (measured minus predicted) shows surge.
- *On the globe*: a global tide atlas reduced to 8 constituents and packed into one texture, as the reference site does with FES2022. FES2022 and TPXO have licence conditions to check; EOT20 is an openly published alternative to evaluate first.

If the buoys do not measure water level, station tide predictions fall back to
the global atlas at the buoy's position.

## 16. Still open

1. A sample CSV (header row and a few lines) from one station — this fixes the column map, units, time zone and reporting interval.
2. Does any station record water level or pressure? This decides the tide source at the buoys.
3. The operation types to support and their limits, or the person who can supply them.
4. How the CSVs are reached on the server: file path, HTTP, SFTP or a database export, and how often they update.
5. Is the site public, or behind a login for staff and clients?
