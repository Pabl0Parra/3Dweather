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

## 4. First runs

1. **Actions** → **Static assets** → **Run workflow**. This uploads the land
   mask, the coastline, one outline per regional map (`regions/{region}.json`)
   and the tide atlas (`tide.json` and the `tide-<hash>.png` it names) to
   `assets/globe/`. The first run downloads EOT20 (2.3 GB, cached afterwards)
   and takes about 15 minutes. It also builds the station catalogue from the NOAA
   CO-OPS station list and GeoNames (`stations.json`, `search.json`,
   `countries.json`) and uploads it to `catalogue/`. Run it again when you want
   a fresh catalogue, then run **Site**.
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
   `main`). It downloads `catalogue/stations.json` from the bucket, builds the
   site with one page per station (about 24,500 pages, about a minute) and
   uploads it to the root of the bucket. Only files whose content changed go up;
   `site-manifest.json` in the bucket remembers what was published, so pages
   that leave the catalogue are deleted. It never touches `wx/`, `assets/` or
   `catalogue/`. The first upload sends every page and takes several minutes.

Check it: `https://pub-….r2.dev/us/new-york/new-york-city` should show the New
York City page.

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

## Files and cache lifetimes

| Key | Cache-Control |
|---|---|
| pages (`us/…`, `wave-map`, …) | `public, max-age=3600` |
| `_astro/*` | `public, max-age=31536000, immutable` |
| `catalogue/*` | `public, max-age=86400` |
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
