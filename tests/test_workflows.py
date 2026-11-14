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


def test_no_secret_values_in_workflows():
    for f in WF.glob("*.yml"):
        body = f.read_text(encoding="utf-8")
        assert "r2.cloudflarestorage.com" not in body, f.name  # the endpoint is built from the secret in code
