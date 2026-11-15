# Publishing the forecast (owner setup)

GitHub Actions builds every forecast run and uploads it to a Cloudflare R2
bucket; visitors' browsers download the files straight from R2. There is no
server. Everything below is a one-time setup in the Cloudflare dashboard and
the GitHub repository settings. No secret goes into the repository.

## 1. Create the bucket

1. Cloudflare dashboard → **R2 Object Storage** → **Create bucket**. Name it,
   for example, `3dweather`. Location: automatic.
2. Open the bucket → **Settings** → **Public access** → **R2.dev subdomain** →
   **Allow access**. Note the address it shows (`https://pub-….r2.dev`).
   Cloudflare rate-limits this address and does not cache it: it is fine for
   building and testing, not for launch. Before launch, connect a custom domain
   in the same panel instead.
3. **Settings** → **CORS policy** → paste, replacing the origins with where the
   site will be served (keep `http://localhost:4321` for local development):

   ```json
   [
     {
       "AllowedOrigins": ["http://localhost:4321", "https://your-site.example"],
       "AllowedMethods": ["GET", "HEAD"],
       "AllowedHeaders": ["*"],
       "MaxAgeSeconds": 86400
     }
   ]
   ```

## 2. Create an API token for the bucket

R2 → **Manage API tokens** → **Create API token**:
- Permissions: **Object Read & Write**.
- Specify bucket: only the bucket from step 1.
- TTL: forever (or set a reminder to rotate it).

Copy the **Access Key ID** and **Secret Access Key** (shown once) and your
**Account ID** (R2 overview page, right-hand side).

## 3. Add the GitHub Actions secrets

Repository → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**, four times:

| Secret | Value |
|---|---|
| `R2_ACCOUNT_ID` | the Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | the token's access key ID |
| `R2_SECRET_ACCESS_KEY` | the token's secret access key |
| `R2_BUCKET` | the bucket name, e.g. `3dweather` |
| `R2_PRIVATE_BUCKET` | optional: a second bucket, **not** public, for FES2022 (section 7) |

The token from step 2 needs read and write access to the private bucket too.

## 4. First runs

1. **Actions** → **Static assets** → **Run workflow**. This uploads the land
   mask, the coastline, one outline per regional map (`regions/{region}.json`)
   and the tide atlas (`tide.json` and the `tide-<hash>.png` it names) to
   `assets/globe/`. The first run downloads EOT20 (2.3 GB, cached afterwards)
   and takes about 15 minutes. It also builds the station catalogue from the NOAA
   CO-OPS station list and GeoNames (`stations.json`, `search.json`,
   `countries.json`) and uploads it to `catalogue/`. Run it again when you want
   a fresh catalogue, then run **Site**. Last, it builds `tide-constants.json`:
   NOAA's harmonic constants and subordinate offsets for every NOAA station,
   a nearby NOAA station's tide for places within 5 km of one, and the global
   tide model (EOT20, or FES2022 where you have supplied it) everywhere else.
   NOAA is asked one request at a time; the first run makes about 4,700
   requests (about an hour) and later runs reuse the cached answers, which are
   kept even when a run fails and refreshed once a year. If NOAA
   refuses requests the job fails rather than publish constants with NOAA
   stations on the model; run it again later and it carries on from the cache.
   Without a private bucket the file goes to `catalogue/tide-constants.json`;
   with one it goes to `tides-private/tide-constants.json` in that bucket.
2. **Actions** → **Forecast run** → **Run workflow** (leave the run empty).
   It builds the run that is due now and uploads it to `wx/<run>/`, then
   `wx/latest.json`. Each run folder also holds the 12 regional maps
   (`{region}.json`, `{region}-a.webp`, `{region}-b.webp`), and `latest.json`
   lists them under `"regions"`. Expect 20–40 minutes. If the inputs are not all published
   yet it waits up to 90 minutes, then fails with exit code 2 and the reason in
   the log; nothing is uploaded in that case.
3. From then on the schedule runs it four times a day (05:15, 11:15, 17:15 and
   23:15 UTC, with a retry an hour after each). A run that is already published
   exits within a minute. Runs older than 3 days are deleted.

Check it worked: `https://pub-….r2.dev/wx/latest.json` should name the run.
4. **Actions** → **Site** → **Run workflow** (it also runs on every push to
   `main`, and every day at 00:30 UTC). It downloads `catalogue/stations.json`
   and `tide-constants.json` from the bucket (from `R2_PRIVATE_BUCKET` when that
   secret is set), writes each station's month of tides, sun and moon
   (`python -m pipeline station-data`, about 2 minutes; the first run of a
   month also computes the month's sun and moon, about 45 minutes), builds the
   site with one page per station (about 24,500 pages, about 5 minutes, 1.3 GB) and
   uploads it to the root of the bucket. The month's sun and moon data are
   computed on the first run of each month and kept in the Actions cache
   (`sky-months`), so later days are quicker. Pages read the weather from `wx/`
   and other months from `tides/` in the browser. Without `tide-constants.json`
   the pages are built without tide data and say the table is on its way.
   Every station page changes each day, so a daily run uploads about 24,500
   files (about 735,000 writes a month, inside R2's free 1 million). Only files whose content changed go up;
   `site-manifest.json` in the bucket remembers what was published, so pages
   that leave the catalogue are deleted. It never touches `wx/`, `assets/` or
   `catalogue/`. The first upload sends every page and takes several minutes.
   Site also runs by itself after each successful Static assets run, so a new
   catalogue gets its pages at once. Two safety stops: if the catalogue cannot
   be downloaded the job fails instead of publishing a site without station
   pages, and a publish that would delete more than 10 % of the site stops
   (run `python -m pipeline publish-site --allow-mass-delete` by hand if that
   is really intended). Replaced `_astro/` scripts stay two days, so pages
   cached before a deploy keep working.

Check it: `https://pub-….r2.dev/us/new-york/new-york-city` should show the New
York City page.
5. **Actions** → **Tides** → **Run workflow** (afterwards it runs by itself at
   02:00 UTC on the 1st of each month). It downloads the catalogue and
   `tide-constants.json`, computes high and low waters for every station from
   12 months before the current month to 12 months after, and uploads one file
   per station to `tides/{country}/{region}/{station}.json`, plus
   `tides/index.json` listing the stations without tides (inland places more
   than 20 km from model ocean). Run it again after Static assets has rebuilt the
   constants.

## 5. Where the site is served

Pages, `wx/`, `assets/` and `catalogue/` all live in the same bucket, so the
site reads its data from its own address (the Site workflow builds with
`PUBLIC_WX_BASE=/wx`, `PUBLIC_ASSET_BASE=/assets/globe` and
`PUBLIC_CATALOGUE_BASE=/catalogue`). Cloudflare Pages was ruled out: its free
plan stops at 20,000 files and the site has about 24,500 pages.

Every page is stored without `.html` (`us/new-york/new-york-city`, `wave-map`)
with an HTML content type, so clean URLs work with no routing rule. The one
exception is the bare domain: R2 has no index document, so `/` needs one rule
once a custom domain is connected (**Rules** → **Transform Rules** → **Rewrite
URL**: when the path equals `/`, rewrite the path to `/index.html`). On the
`r2.dev` address, open a page such as `/wave-map` instead.

## 6. Building the site somewhere else

To serve the site from another host, build it with the bucket's address (for
example in that host's build settings, or a local `web/.env` file, which is
git-ignored), and add that host to the CORS policy:

```
PUBLIC_WX_BASE=https://pub-….r2.dev/wx
PUBLIC_ASSET_BASE=https://pub-….r2.dev/assets/globe
```

Without them the site reads `/wx` and `/assets/globe` from its own folder,
which is how local development works (`python -m pipeline build … --out
web/public/wx --latest`, `python -m pipeline static … --out
web/public/assets/globe`, `python -m pipeline tide-atlas --eot20 eot20/eot20.zip
--out web/public/assets/globe`).

## 7. FES2022 (optional, on your own machine)

FES2022 is the tide model the reference site uses; its licence (AVISO+) lets
you use it but not pass its values on, so it never goes into the repository, a
GitHub runner or the public bucket. Until you supply it, places use EOT20.

1. Register at AVISO+, ask for the FES2022 ocean tide product, and download the
   ocean-tide netCDF files (`m2_fes2022.nc`, `k1_fes2022.nc`, …) into one folder.
2. Create a second R2 bucket with public access **off**, and add its name as the
   `R2_PRIVATE_BUCKET` secret (section 3).
3. Download the current catalogue (`catalogue/stations.json` from the public
   bucket), then:

   ```
   python -m pip install -e ".[publish,tides]"
   python tools/fes2022_constants.py --catalogue stations.json --fes <FES folder> --out fes/model-constants.json
   python -m pipeline upload --src fes --prefix fes2022 --max-age 0 --store r2:<private bucket>
   ```

   (with the four `R2_*` variables set in your shell as in section 3).
4. Run **Static assets**, then **Tides**. FES2022 now comes first at every place
   it covers and EOT20 fills the rest. Repeat step 3 when the catalogue changes;
   new places use EOT20 until you do.

## Files and cache lifetimes

| Key | Cache-Control |
|---|---|
| pages (`us/…`, `wave-map`, …) | `public, max-age=3600` |
| `_astro/*` | `public, max-age=31536000, immutable` |
| `catalogue/*` | `public, max-age=86400` |
| `tides/*` | `public, max-age=86400` |
| `wx/latest.json` | `public, max-age=60` |
| `wx/<YYYYMMDDHH>/*` | `public, max-age=2592000, immutable` |
| `assets/globe/*` | `public, max-age=604800` |

## Notes

- `python -m pipeline cycle` always deletes downloaded inputs as it goes
  (`--prune`); never point its `--cache` at a folder of saved inputs you want
  to keep, such as `reference/openmeteo-inputs`.
- Without the secrets (before setup, or on a fork) scheduled runs do nothing
  but print a notice. A manual run builds into a temporary folder and skips the
  upload, which is a way to try the build.
- An explicit run that is not newer than the published one is skipped: the
  published run never moves backwards.
- The **Keep-alive** workflow makes an empty commit on the 1st of each month,
  because GitHub pauses scheduled workflows after 60 days without activity.
