# 3Dweather data design: same sources as thetidechart.com, our own files

Date: 2026-11-14. Status: approved by the owner on 2026-11-14.
The site is non-commercial and open source (owner, 2026-11-14), which is the
use the FES2022 and Open-Meteo terms are most permissive about. Designer's
calls still open to correction: the site is named 3Dweather, its written
content (guides, FAQs) is written fresh and templated per station, and the
code licence is MIT unless the owner prefers another.
Repository: https://github.com/Pabl0Parra/3Dweather (public). The project was
first called Waves5; older notes use that name.

This replaces sections 8, 9 and 11-16 of `docs/wave-map-findings-and-plan.md`.
The owner discarded own buoys, CSV ingestion and marine operations on
2026-11-14, and on the same day chose to run no back-end server: the data is
built by scheduled GitHub Actions jobs and the site is static files. That
removes FastAPI and MySQL from the stack chosen earlier. Sections 1-7 and 10 of
that document remain the reference for formats, rendering and site structure.

Evidence behind this design: the 2026-11-13 capture in
`reference/thetidechart-capture/`, and three research passes on 2026-11-14
(shipped files, provider documentation, and a live REA capture of all layers).

## 1. Intent

3Dweather replicates thetidechart.com: the weather globe with six layers, the
regional maps, and the station pages. It must show the same underlying data as
that site. We get there by pulling the same public datasets the site names and
building our own files from them, not by copying the site's files.

Why not their files: their terms say "don't scrape the site at volume; the open
data behind it is yours to use on its own licences"; their data files carry no
CORS header, so a page on another domain cannot read them; and a mirror would
break whenever they change anything.

## 2. Goals, non-goals, anti-goals

Goals
- Every number on the globe and regional maps comes from the same model, run
  and variable as the reference site, so that values agree to within encoding
  rounding.
- Tide tables, sun/moon data and station weather come from the same named sources.
- A new forecast run is published every 6 hours without manual work.
- Every source is credited as its licence requires.
- No always-on server: scheduled jobs write files, and visitors read files.

Non-goals
- Accounts, synced favourites and alert e-mails in the first version. They need
  server-side code; favourites and unit preferences live in the browser only.
  If wanted later they are added as serverless functions with a managed database.
- Byte-identical files. Resampling and rounding will differ slightly.
- Reproducing rules the site does not publish (section 8). We write our own and
  say so.
- Own-buoy data, CSV ingestion, marine-operations workability.

Anti-goals
- Fetching or proxying data files from thetidechart.com in production.
- Copying their JavaScript, CSS, text, logo or audio.
- Showing data without the attribution its licence requires.

## 3. Approaches considered

| | Approach | Trade-off |
|---|---|---|
| A | **Open-Meteo public bucket** (`s3://openmeteo`) for all forecast grids | Same feed the reference site uses, so variables and run times match best. One format, no accounts. Depends on Open-Meteo's bucket and its `.om` format |
| B | Each provider directly (NOAA and ECMWF on AWS, Copernicus Marine) | No middleman. Three formats, a Copernicus account, and derived fields (rain rate, total current) computed differently from the reference |
| C | Self-hosted Open-Meteo server, as the reference site runs | Gives a point API with the multi-model wave blend. Heavy server, constant sync, AGPL code |

**Chosen: A.** The owner chose "same sources, build our own files"; choosing A
among the fetch routes is the designer's call. B stays available per source
behind the same interface if the bucket fails us. C is the fallback only if
sampling grids proves too coarse for station pages.

## 4. Sources

| Data | Dataset | Open-Meteo bucket model | Variables | Licence / credit |
|---|---|---|---|---|
| Wind, rain, cloud, air temperature | NOAA GFS | `ncep_gfs013` | `wind_u_component_10m`, `wind_v_component_10m`, `precipitation`, `cloud_cover`, `temperature_2m` | NOAA open data; Open-Meteo CC BY 4.0 |
| Pressure, gusts | ECMWF IFS, previous cycle (6 h behind) | `ecmwf_ifs` (9 km) | `pressure_msl`, `wind_gusts_10m` | CC BY 4.0 |
| Waves | NOAA GFS-Wave | `ncep_gfswave025` | `wave_height`, `wave_period`, `wave_direction` | NOAA open data |
| Currents, sea temperature | Mercator global physics (Copernicus Marine), daily | `meteofrance_currents`, `meteofrance_sea_surface_temperature` | `ocean_u_current`, `ocean_v_current`, `sea_surface_temperature` | "E.U. Copernicus Marine Service Information" |
| Storm index inputs | NOAA GFS | `ncep_gfs025` | `cape`, `precipitation` | as GFS |
| Air quality (station pages) | CAMS | CAMS models in the bucket (names to confirm in phase 8) | European AQI, O3, PM10, PM2.5 | Copernicus CAMS credit |
| Tide layer; tide tables outside NOAA coverage | FES2022 ocean tide, 34 constituents, 1/30° | – (AVISO+ download) | amplitude and phase per constituent | AVISO licence; credit CNES/LEGOS/NOVELTIS/CLS/AVISO |
| US tide tables | NOAA CO-OPS harmonic constants and subordinate offsets | – (CO-OPS metadata API) | constituents, offsets | Public domain; state "not NOAA's official predictions" |
| Sun, moon, coefficient, solunar | JPL DE421 ephemeris | – | – | Free (NASA/JPL) |
| Station catalogue | NOAA CO-OPS station list, GeoNames | – | – | Public domain; CC BY 4.0 |
| Base map art | Natural Earth, NASA Black Marble, Yale Bright Star Catalogue | – | – | Public domain |
| Finder map tiles | OpenStreetMap | – | – | ODbL |

Run alignment for a globe run at time T (matches the reference `sources`
field): GFS and GFS-Wave run T; IFS run T − 6 h; currents and sea temperature
the newest daily run available at build time (about 30 h behind).

Pressure and gust coverage (observed on four reference runs, 2026-11-13/14):
- The IFS run used is always the cycle before T, including the short 06Z and
  18Z runs, which end 144 h after their own start (138 h after T).
- Gusts are published only to 84 h (`gustHours: 84`) on every run. That is
  where the IFS run stops being hourly; we do the same and stop gusts there.
- Pressure covers all 168 h on every run. For T = 06Z/18Z the IFS run is a long
  00Z/12Z run that steps 6-hourly after its own hour 144; frames between two
  steps take their linear mean in time (matched run 2026111306 to 0.1 hPa at
  every odd frame 141-165). For T = 00Z/12Z the short IFS run ends at T+138;
  designer's call: fill from GFS `pressure_msl` of run T (`ncep_gfs025`). That
  fallback is unchecked until a 00Z or 12Z reference capture exists.

Grids as found in the bucket: GFS 13 km is 3072×1536 regular; GFS 0.25° and
GFS-Wave are 1440×721; IFS is the O1280 reduced Gaussian grid (6,599,680
points in one row), which needs its own regridding step.

The owner is registering the AVISO+ account and will download FES2022. EOT20
(CC BY 4.0, direct download) is the stand-in until that licence is in hand, and
is clearly not "the same data".

### Where the jobs run (owner's choice: GitHub Actions)

| | Option | Trade-off |
|---|---|---|
| 1 | **GitHub Actions on a schedule** (chosen) | Free for a public repository; nothing to operate. Scheduled starts can be late, jobs are capped at 6 h, and the runner has about 14 GB of free disk |
| 2 | Cloud job on a timer next to the bucket (AWS `us-west-2`) | Fast, predictable, a few dollars a month. An AWS account to manage |
| 3 | The owner's PC on a timer | Free, but only while the machine is on, and 80 GB a day over a home connection |

The pipeline is a plain Python command, so moving from 1 to 2 later changes
only the trigger.

## 5. Pipeline (Python, run by GitHub Actions)

Schedule: 00, 06, 12, 18Z runs. A workflow starts by cron about 5 h 15 min
after each nominal time, and can also be started by hand. It first reads the
bucket's `latest.json` for each model; if the run is not complete it waits and
re-checks for up to 90 minutes, then fails loudly. It never publishes a partial
run. If the newest published run is already current it exits at once, so a
second cron entry an hour later serves as a retry for late or skipped starts.

GitHub Actions constraints the pipeline is built around:
- **Disk** (about 14 GB free): input files are processed one time step at a
  time and deleted, never all held at once.
- **Minutes**: a run is expected to take 20-40 minutes. A public repository is
  free. A private one has 2,000 free minutes a month, which four runs a day
  would exceed; assumed public unless the owner says otherwise.
- **Idle shut-off**: GitHub disables scheduled workflows in a public repository
  after 60 days without commits; a monthly keep-alive commit by workflow
  prevents it.
- **Secrets**: storage credentials are GitHub Actions secrets. Nothing licensed
  or secret is committed.

Steps per run
1. **Fetch** whole-grid `.om` files from `data_spatial/<model>/...` for the
   needed valid times. One `Source` class per dataset behind a common interface
   returning `(variable, valid_time) -> lat/lon grid`. Download each file whole
   and read it locally with the `omfiles` library: reading single variables
   remotely by range request measured about 50 times slower. A full run needs
   roughly 20 GB of transfer (IFS 130 MB, GFS 0.25° 110 MB, GFS 13 km 38 MB
   per time step); files are deleted once their variables are extracted.
2. **Regrid** to the globe grid (768×384, 0.46875°, 3-hourly, 168 h, 57 frames)
   and to each of 12 regional grids (0.234375°, hourly, 72 h, 73 frames).
3. **Derive**: wave travel vector from direction and period; storm index
   (section 8); daily currents frames; fill land cells in sea layers.
4. **Encode** to lossless WebP sprites with the byte encodings in section 4 of
   the findings document. Globe: families `a`, `b`, `t`, `w`, `s` in 7
   day-chunks (4 columns), plus one `c` file. Regions: `{region}-a`, `{region}-b`
   (8 columns).
5. **Manifests**: `globe.json` and `{region}.json` with grid, frame counts,
   feature flags (`gustHours` etc.), `sources` run times and hourly `peaks`.
6. **Station sampling**: sample the full-resolution grids at every station
   position (nearest sea cell for marine variables) and write one compact JSON
   file per region, `wx/{run}/stations/{cc}/{region}.json`, holding every
   station in it. About 1,400 files per run instead of 24,600, which keeps
   storage write operations inside the free allowance.
7. **Publish**: upload to object storage under `wx/{YYYYMMDDHH}/`, switch
   `wx/latest.json` last, prune runs older than 3 days.

Static, built once (not per run): land mask and city lights, coastline, rivers,
terrain texture and tiles, star catalogue, regional coast outlines, and the
tide atlas texture (8 constituents of FES2022 at 0.5°, with monthly nodal
factors).

The file layout and encodings are kept compatible with the reference format on
purpose: it lets us test our output against the captured reference run.

## 6. Station data

**Catalogue.** NOAA CO-OPS stations (type `gauge`) plus GeoNames coastal places
(type `place`), grouped by country and region, with time zone and island. The
reference has about 24,630 stations in 190 countries. Record schema as in
section 10 of the findings document.

**Tides.** Predicted in a scheduled job by harmonic synthesis, heights in metres
from mean sea level, astronomical tide only. Constants per station, following
the rules the reference site publishes:
- NOAA harmonic station: NOAA's constants.
- NOAA subordinate station: NOAA's time and height offsets applied to its
  reference station, only if that station is within 1,000 km; otherwise FES2022.
- Place within 5 km of a usable NOAA station: that station's tide, donor named
  on the page.
- Everything else: FES2022 at the place's position, nearest ocean cell within
  20 km when the point falls on land.

FES2022 is several gigabytes and licensed to the owner, so it never goes into
the repository or onto a runner. A one-off script, run on the owner's machine
where FES2022 sits, extracts the constants for every non-NOAA station into one
file. That file is kept in a private storage bucket and downloaded by the jobs.
It is re-run only when the catalogue changes.

Outputs, written as static files:
- Per station, one file with high and low water times and heights for 12
  months either side of today (about 3,000 turns). Rebuilt monthly. The
  "other months" view and CSV export read it directly.
- Today's 10-minute curve and the 30-day block, embedded in the station page.

**Astronomy.** From DE421 (via `skyfield`): sunrise, sunset, transit, twilight,
golden and blue hour, moon phase, illumination, rise, set and distance, solunar
major periods (2 h around moon transit and anti-transit) and minor periods
(1 h around moonrise and moonset), and the tidal coefficient (20-120 scale).

**Weather and sea.** Read by the browser from the per-run region files (step 6 above):
temperature, wind, gusts, rain, cloud, pressure, UV, sea temperature, wave
height, period and direction, air quality. Station pages show today plus 7 days.
Designer's call on accuracy: sample each model's native grid at every hour it
provides (GFS 13 km is hourly to 120 h, then 3-hourly), nearest cell, no
downscaling. Open-Meteo's own point API adds elevation correction and blends
several wave models, so coastal values can differ from the reference by a
degree or a few tenths of a metre. That is accepted. A self-hosted Open-Meteo
server (approach C) is added only if the owner asks for closer agreement.

**Serving.** The reference site serves one cached page per station with 30 days
of tide and sky data embedded as JSON, and lets the browser handle "now", unit
conversion and chart drawing. We do the same with static pages: a daily job
rebuilds every station page with its 30-day block, and the browser adds the
weather from the newest run. Where the reference prints weather into the HTML
(the 2-hourly strip, 7-day outlook, pressure, UV, air quality), ours is filled
in by the browser after load. Search engines therefore see tides and sky data
in our pages but not the weather figures; that is the one visible cost of
having no server.

**Search, nearest and map markers.** One static catalogue file (id, name,
country, region, position, type, path for all stations; about 1-2 MB
compressed) loaded on demand and searched in the browser. It replaces the
reference's `/api/stations` endpoints.

## 7. Jobs, storage and hosting

Scheduled GitHub Actions workflows

| Workflow | When | Writes |
|---|---|---|
| Forecast run | Every 6 h | Globe and regional sprites, manifests, station weather files, `latest.json` |
| Station pages | Daily | All station, region and country pages with the 30-day tide and sky block |
| Tide tables | Monthly | Per-station 25-month high and low water files |
| Catalogue and static assets | By hand | Station catalogue, base map art, tide atlas texture |
| Keep-alive | Monthly | An empty commit so schedules stay enabled |

Storage and hosting (designer's call: Cloudflare)
- **Object storage (Cloudflare R2)** holds everything visitors download: `wx/`
  runs, tide tables, the catalogue, static assets and the built pages. R2 does
  not charge for downloads. A second, private bucket holds the tide constants.
- **CDN and domain (Cloudflare)** in front, with the cache lifetimes the
  reference uses: 60 s for `latest.json`, 30 days for a run's files, a week
  for static assets.
- **Pages**: about 26,000 HTML files. That is above the 20,000-file limit of
  Cloudflare Pages' free plan (to confirm in phase 7), so pages are uploaded to
  R2 as well, with a small routing rule for clean URLs. The daily job uploads
  only pages whose content changed.
- **No database, no API server.** Run history is the set of run folders;
  `latest.json` is the only pointer.

Software
- **Python** for every job (pipeline, tides, astronomy, catalogue).
- **Astro + TypeScript** building static pages; the globe, regional map,
  charts and search as framework-free TypeScript modules.

## 8. Known differences from the reference

These cannot be matched from outside; each is our own rule, documented as such.

| Item | What we know | Our approach |
|---|---|---|
| Thunderstorm index | 0-255 per cell, mostly tropical, 78 % overlap with rain; formula unpublished | `0.1·CAPE^0.75`, scaled by rain up to 3 mm/h, zero where the lifted index is positive (GFS 0.25°). Storm cells overlap the reference's by 38 % (phase 3a) |
| Daily currents frame | One frame per day; snapshot or mean unknown | Snapshot at T+24k h (measured in phase 3a: snapshot 0.04 byte levels, daily mean about 3) |
| Cloud | Byte scale and source unpublished; GFS total cloud cover is 45 byte levels off | Ours: max(low, mid) + 0.3·high·(1 − max/100) from GFS 13 km, linear byte; about 17 byte levels off. The readout's cloud % is this blend |
| Wave period and direction | Inferred to be GFS-Wave primary period and direction | Use those; confirm in the reference test |
| GFS grid for the globe | 13 km or 0.25° unknown; resampled to 0.47° either way | 13 km, averaged over the 4×4 source cells in each globe cell (matches exactly) |
| Station wave data | Reference uses Open-Meteo's multi-model marine blend | GFS-Wave only, same as the globe |
| Catalogue selection | GeoNames feature classes and coast-distance cut-offs unpublished | Our own rule, tuned to land near the reference counts |
| Tidal coefficient | From the ephemeris, formula unpublished | Standard French formula; check against captured values |
| Activity and solunar ratings | Some thresholds visible in page text only | Our own rules, starting from the visible thresholds |
| FES2022 details | Product variant and nodal scheme unknown | Ocean tide, extrapolated grids, `aviso-fes` prediction code |

## 9. Verification

- **Reference run test.** Rebuild run `2026111306` from the bucket and compare
  with the captured `globe-a0/b0/t0/w0/s0/c` sprites and `peaks`. Pass: mean
  absolute difference of at most 2 byte levels per channel over sea or land
  cells as applicable, and peak positions within 2 grid cells. The bucket keeps
  whole grids for only 7 days, so the inputs for that run were saved on
  2026-11-14 with `tools/save_reference_inputs.py` into
  `reference/openmeteo-inputs/2026111306/` (format described in that script).
  Only day-chunk 0 of the reference sprites was captured, so the test covers
  the first 21 hours. For later hours or other cases, capture a fresh pair at
  any time: the bucket holds the last 7 days and the reference site the last
  2 days of runs.
- **Phase 1 results (2026-11-14, wave layer).** Built from the saved inputs
  and compared with the captured reference sprite, frames 0-7 (hours 0-21):
  - Open-sea cells (65 % of the grid): 99.95 % identical bytes in wave height
    and 99.94-99.95 % in each vector channel; mean byte difference below 0.001.
  - Hourly peaks: all 169 entries identical in height and position.
  - Grid and frame fields of the manifest: identical.
  - Rules this confirmed: bilinear regridding that skips missing cells, then
    rounding; vector = travel direction with length period ÷ 25; a peak is the
    highest globe cell of the regridded field (not the native grid's maximum,
    which matched only 60 % of frames).
  - Not matched: cells on land and along the coast. Counting every cell, 81 %
    of bytes are identical. The reference extends sea values into land by a
    rule we have not identified; ours spreads them 4 cells. The globe's land
    mask hides most of this, so it is left for the globe phase to judge by eye.
  - GFS has no cloud cover or rain at the analysis hour (hour 0), which
    explains the empty cloud channel in the reference's first frame.
- **Phase 3a results (2026-11-14, every other layer).** Same run, frames 0-7
  of chunk 0 and all 8 daily ocean frames. Mean absolute byte difference:
  - Wind u and v, air temperature: 0.00. The globe cell is exactly 4×4 GFS 13 km
    cells, and the reference averages them (bilinear sampling was 0.2-0.3 off).
  - Rain: 0.03 (frames 1-7). The rule is the mean rate over the hour before and the
    hour after the frame, with a missing hour left out, 4×4 averaged, then smoothed
    with a separable [1, 4, 1]/6 kernel. Steps are weighted by overlap, so the
    3-hourly part past 120 h uses the same rule.
  - Pressure: 0.11 (IFS, which stores pressure in Pa). Gust: 0.9 (IFS).
  - Current u/v and sea temperature: 0.03-0.04 over open sea, as snapshots.
  - Cloud: about 17, our own rule (section 8). Storms: 38 % overlap, our own rule.
  - Peaks: wind, hot, current and cold agree at every hour. Cold leaves out Natural
    Earth glaciated areas, which matched every hour exactly. Sea temperature
    values agree every hour; it is taken over open sea only, and where two spots
    tie the cell can differ. Gusts are within a median of 1.2 m/s. Low pressure
    agrees at every hour once frames between the long IFS run's 6-hourly steps
    are interpolated in time (the first draft filled them from GFS, which made
    pressure flicker frame to frame). Rain agrees except at hours 72-119, where neither the
    hourly nor a 3-hourly reading reproduces the reference; the inputs were
    saved a day after the reference built the run.
- **Tide test.** New York City, November 2026: our high and low waters against
  the captured station data, within 2 minutes and 2 cm. The reference site's
  own FES-vs-NOAA comparison gives the expected error for FES stations.
- **Tide atlas test.** Our per-constituent maximum amplitudes against the
  `amax` values in the captured `tide.json`.
- **Decode test.** Every encoding round-trips within one byte level.

## 10. Build order

Each phase gets its own implementation plan.

1. Pipeline core: bucket reader, globe grid, wave sprites, manifest, reference run test. Save the reference inputs first.
2. Globe: projection, land, coast, gestures, deep link, wave layer, timeline, particles, probe; then the "Ignition" splash screen (`2026-11-14-splash-screen-design.md`).
3. Remaining globe layers: wind, rain and cloud, temperature, pressure and gusts, storms, currents and sea temperature.
4. Scheduling and publishing: Git repository on GitHub, R2 buckets, the 6-hourly workflow, retries, pruning.
5. Tide atlas and tide layer (FES2022; EOT20 until licensed).
6. Regional maps: 12 regions.
7. Station catalogue, static search file, page hosting.
8. Tide prediction engine, FES2022 constants extraction, astronomy, station sampling; monthly tide-table workflow.
9. Station pages and charts; daily page workflow.
10. Site shell: home, country and region pages, finder map, guides, SEO.
11. Embed widget.

Not scheduled: accounts, synced favourites and alert e-mails (section 2).

Owner's accounts (given 2026-11-14): the public GitHub repository above and a
Cloudflare account. The Cloudflare account ID and the R2 access keys are stored
as GitHub Actions secrets, not in the repository. Still needed before phase 4:
an R2 API token created by the owner.

There is no domain name yet. Until there is, files are served from R2's
`r2.dev` development address, which Cloudflare rate-limits and does not cache;
it is good enough to build and test against, not to launch on. A domain is
needed before public launch.

Because the repository is public, `reference/` is git-ignored: the capture
contains the reference site's own code, fonts and images, and the saved model
inputs are several gigabytes. Both stay on the owner's machine.

## 11. Left to the builder

Library choices within Python and TypeScript, the layout of the station
weather and tide-table files, the catalogue file format, regional grid bounds for the 11 regions not captured (derive
from each region's extent and capture the reference manifests for comparison).
