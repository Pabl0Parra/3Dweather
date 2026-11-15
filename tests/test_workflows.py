"""Text checks on the GitHub Actions workflows (no YAML dependency)."""
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def text(name):
    return (WF / name).read_text(encoding="utf-8")


def test_forecast_schedule_concurrency_and_secrets():
    t = text("forecast.yml")
    assert "cron: '15 5,11,17,23 * * *'" in t and "cron: '15 0,6,12,18 * * *'" in t  # due time + an hour-later retry
    assert "workflow_dispatch:" in t
    assert "group: forecast" in t and "cancel-in-progress: false" in t
    assert "timeout-minutes: 180" in t
    for name in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        assert f"secrets.{name}" in t
    assert "python -m pipeline cycle" in t and "--store r2" in t
    assert "--store dir:" in t  # dry run when the secrets are not set (forks, before setup)


def test_static_upload_is_manual_with_a_week_cache():
    t = text("static.yml")
    assert "workflow_dispatch:" in t and "schedule:" not in t
    assert "python -m pipeline static" in t and "--prefix assets/globe" in t and "--max-age 604800" in t


def test_keepalive_monthly_with_write_permission():
    t = text("keepalive.yml")
    assert "cron: '0 3 1 * *'" in t and "contents: write" in t and "--allow-empty" in t


def test_ci_runs_both_suites():
    t = text("ci.yml")
    assert 'pytest -m "not reference"' in t and "npx vitest run" in t and "npm run build" in t
    # The tide and sky tests run too (they skip without h5py or skyfield); DE421 is cached.
    assert '.[dev,publish,tides,sky]' in t and "path: sky-cache" in t and "SKY_CACHE: sky-cache" in t


def test_no_secret_values_in_workflows():
    for f in WF.glob("*.yml"):
        body = f.read_text(encoding="utf-8")
        assert "r2.cloudflarestorage.com" not in body, f.name  # the endpoint is built from the secret in code


def test_scheduled_runs_without_secrets_do_nothing():
    """No dry-run builds on the schedule before setup or on forks (each one downloads ~16 GB)."""
    t = text("forecast.yml")
    assert "EVENT: ${{ github.event_name }}" in t
    assert 'if [ -z "$R2_BUCKET" ] && [ "$EVENT" = schedule ]; then' in t


def test_static_builds_and_uploads_the_tide_atlas():
    """EOT20 (CC BY 4.0) from SEANOE, cached between runs; tide.png and tide.json go up with the art."""
    t = text("static.yml")
    assert "https://www.seanoe.org/data/00683/79489/data/85762.zip" in t
    assert "actions/cache@v4" in t
    assert '.[publish,tides]' in t
    assert "python -m pipeline tide-atlas --eot20" in t and '--out "$RUNNER_TEMP/static"' in t


def test_static_builds_and_uploads_the_catalogue():
    t = text("static.yml")
    assert "python -m pipeline catalogue --inputs" in t
    assert "--prefix catalogue --max-age 86400" in t


def test_static_builds_tide_constants_with_fes2022_kept_private():
    t = text("static.yml")
    assert "python -m pipeline model-constants --catalogue" in t
    assert "python -m pipeline tide-constants --catalogue" in t
    # NOAA's per-station responses are cached between runs.
    assert "path: noaa-cache" in t and "restore-keys: noaa-cache-" in t
    # FES2022 constants come only from the optional private bucket, and anything built from them stays there.
    assert "R2_PRIVATE_BUCKET: ${{ secrets.R2_PRIVATE_BUCKET }}" in t
    assert 'python -m pipeline get --key fes2022/model-constants.json' in t and '--store "r2:$R2_PRIVATE_BUCKET"' in t
    assert '--model "$RUNNER_TEMP/models/fes2022.json" --model "$RUNNER_TEMP/models/eot20.json"' in t
    assert '--prefix tides-private --max-age 0 --store "r2:$R2_PRIVATE_BUCKET"' in t


def test_site_builds_with_the_catalogue_and_publishes_changed_files():
    t = text("site.yml")
    assert "branches: [main]" in t and "workflow_dispatch:" in t
    assert "group: site" in t
    assert "python -m pipeline get --key catalogue/stations.json" in t
    assert "CATALOGUE_FILE: ${{ runner.temp }}/stations.json" in t
    assert "PUBLIC_WX_BASE: /wx" in t and "PUBLIC_ASSET_BASE: /assets/globe" in t and "PUBLIC_CATALOGUE_BASE: /catalogue" in t
    assert "npm run build" in t and "python -m pipeline publish-site --dist web/dist --store r2" in t
    assert 'if [ -z "$R2_BUCKET" ]; then' in t  # forks and pre-setup: build, publish nothing
    for name in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        assert f"secrets.{name}" in t


def test_site_fails_on_a_broken_catalogue_download_and_follows_static_assets():
    t = text("site.yml")
    assert "workflow_run:" in t and "workflows: [Static assets]" in t and "types: [completed]" in t
    assert "github.event.workflow_run.conclusion == 'success'" in t
    # Exit 3 (no catalogue yet) builds without stations; any other failure stops the job.
    assert 'if [ "$code" -eq 3 ]; then' in t and 'exit "$code"' in t


def test_tides_run_monthly_and_upload_a_day_cache():
    t = text("tides.yml")
    assert "cron: '0 2 1 * *'" in t and "workflow_dispatch:" in t
    assert "python -m pipeline get --key catalogue/stations.json" in t
    # tide-constants.json from the private bucket when there is one (FES2022), else next to the catalogue.
    assert '--key tides-private/tide-constants.json' in t and '--store "r2:$R2_PRIVATE_BUCKET"' in t
    assert "--key catalogue/tide-constants.json" in t
    assert "python -m pipeline tide-tables --catalogue" in t
    assert "--prefix tides --max-age 86400 --store r2" in t
