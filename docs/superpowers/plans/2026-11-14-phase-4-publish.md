# Phase 4: Scheduling and publishing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A GitHub Actions workflow builds each 6-hourly run with no one watching, uploads it to Cloudflare R2, switches `wx/latest.json` last, and prunes runs older than 3 days. Static globe assets are published by hand. A CI workflow runs the test suites.

**Architecture:**
- `pipeline/publish.py` holds a small `Store` interface with two implementations: `DirStore`, a local folder used by tests and dry runs, and `S3Store`, which uses boto3 against R2's S3 API.
- `pipeline/cycle.py` decides which run is due, exits if that run is already published, waits for the inputs (up to 90 min), builds with `prune=True`, publishes, and prunes old runs.
- The workflows only call the CLI.

**Tech Stack:** Python 3.12+, boto3 1.42.97 (optional extra `publish`), GitHub Actions (`actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`).

**Spec:** `docs/superpowers/specs/2026-11-14-same-sources-data-design.md` §5 (schedule, retries, disk), §7 (jobs, storage, cache lifetimes) and §10 (owner's accounts).

## Global Constraints

- Schedule: runs at 00, 06, 12 and 18Z. Cron fires about 5 h 15 min after each nominal time, plus a second entry an hour later as a retry. A run that is already current exits at once.
- The workflow waits for incomplete inputs for up to 90 minutes, then fails loudly. It never publishes a partial run.
- Cache-Control: `latest.json` 60 s; a run's files 30 days, immutable; static assets 1 week.
- Layout: `wx/{YYYYMMDDHH}/…` and `wx/latest.json`, written last. Static files go under `assets/globe/`.
- Prune `wx/` runs older than 3 days before the run being published. Never prune the run `latest.json` points to.
- Secrets live only in GitHub Actions secrets: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`. Without them the forecast workflow builds the run, then skips the upload with a notice instead of failing.
- A monthly keep-alive stops GitHub disabling the schedules after 60 idle days.

## Review Focus

1. **A crash halfway through the upload.** `latest.json` must still point at the old, complete run. Test in Task 1.
2. **Two runs overlapping**, from a cron retry plus a manual start: workflow concurrency means only one cycle runs at a time. This lives in the workflow file and is checked by review.
3. **Clock edge cases.** At 05:14Z the due run is 18Z of the day before; at 05:15Z it is 00Z. Test in Task 2.
4. **Pruning.** It never deletes the published run or anything outside `wx/`, and it ignores foreign keys (`wx/latest.json`, `wx/notes.txt`). Test in Task 1.
5. **A missing secret.** It must not leak values into logs, and it must not fail forks. The workflow `if:` guard does this.

---

### Task 1: Store and publishing

**Files:** Create `pipeline/publish.py` and `tests/test_publish.py`. Modify `pyproject.toml`.

**Produces:**
- `Store` protocol with:
  - `put_file(key, path, content_type, cache_control)`
  - `put_bytes(key, data, content_type, cache_control)`
  - `get_bytes(key) -> bytes | None`
  - `list_keys(prefix) -> list[str]`
  - `delete_keys(keys)`
- `DirStore(root)`, which also writes `<key>.meta.json` sidecars holding the headers so tests can check them.
- `S3Store(client, bucket)` and `s3_store_from_env()`.
- `publish_run(store, run_dir, run, built)` uploads every file, then `latest.json`.
- `published_run(store) -> datetime | None`.
- `prune_runs(store, keep_from: datetime) -> list[str]`, which returns the deleted run dirs.
- `upload_dir(store, src, prefix, cache_control)`.

Tests:
- Run files get the 30-day immutable header, and `latest.json` gets `max-age=60`.
- `latest.json` is written last. A store that fails on the third file leaves the old `latest.json` untouched.
- Prune deletes only old run folders. It keeps `keep_from` and newer runs, the published run, and non-run keys.
- `S3Store` calls the client with the right `Bucket`, `Key`, `ContentType` and `CacheControl`, and pages through `list_objects_v2`.

### Task 2: The cycle command

**Files:** Create `pipeline/cycle.py` and `tests/test_cycle.py`. Modify `pipeline/__main__.py` (`cycle`, `upload` subcommands).

**Produces:**
- `due_run(now) -> datetime`: the newest of 00/06/12/18Z with `now ≥ run + 5 h 15 min`.
- `cycle(now, cache_dir, out_dir, store, build=build_run, sleep=time.sleep, wait=timedelta(minutes=90), poll=timedelta(minutes=10)) -> int`. It returns 0 when published or already current, and 2 when inputs are still missing after the wait.
- CLI subcommands:
  - `cycle --cache --out --store (r2|dir:PATH) [--run YYYYMMDDHH]`
  - `upload --src --prefix --max-age --store`

Tests:
- Clock edges.
- Already current: exits with no build.
- Incomplete: retries until it is ready, then publishes.
- Still incomplete after the wait: returns 2, publishes nothing, and `latest.json` is unchanged.
- An explicit `--run` overrides the due run.
- `build` is called with `prune=True`.

### Task 3: Workflows and owner guide

**Files:**
- Create `.github/workflows/ci.yml`, `forecast.yml`, `static.yml`, `keepalive.yml`.
- Create `docs/deploy.md`.
- Modify `README.md`.

What each part does:
- **CI:** pytest without the reference tests; web `npm ci`, `vitest`, `astro build`.
- **Forecast:**
  - Triggers: cron `15 5,11,17,23 * * *` and `15 0,6,12,18 * * *`, plus a manual start with an optional run.
  - `concurrency: forecast` without cancelling, and a 180-minute timeout.
  - Builds into `$RUNNER_TEMP`. When the secrets are missing it uses `--store dir:` and prints a notice.
- **Static:** a manual start that runs `pipeline static`, then `upload` to `assets/globe` with a 1-week max-age.
- **Keep-alive:** on the 1st of each month it makes an empty commit with `contents: write`.
- **Owner guide** covers:
  - creating the bucket and turning on the r2.dev address;
  - CORS JSON;
  - an API token scoped to the bucket;
  - the four secrets;
  - `PUBLIC_WX_BASE` / `PUBLIC_ASSET_BASE` for the web build;
  - a first manual run.
- YAML is checked by a test that parses each workflow and asserts the crons, the concurrency setting and the secret names (PyYAML is already present through pytest? No, so it uses a minimal text check).
