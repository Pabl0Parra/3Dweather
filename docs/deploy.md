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
   and takes about 15 minutes.
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

## 5. Point the site at the bucket

Build the site with the bucket's address (for example in the hosting provider's
build settings, or a local `web/.env` file, which is git-ignored):

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
