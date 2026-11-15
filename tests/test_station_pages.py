import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("skyfield")

from pipeline.sky import load_sky  # noqa: E402
from pipeline.station_pages import station_data, write_station_data  # noqa: E402
from pipeline.tide_tables import station_turns  # noqa: E402

ROOT = Path(__file__).parent.parent
FIX = ROOT / "tests" / "fixtures" / "noaa"
UTC = timezone.utc
NY = ZoneInfo("America/New_York")


@pytest.fixture(scope="module")
def sky():
    return load_sky(Path(os.environ.get("SKY_CACHE", ROOT / "sky-cache")))


def battery_cons():
    d = json.loads((FIX / "8518750-harcon.json").read_text(encoding="utf-8"))
    return [[c["name"], c["amplitude"], c["phase_GMT"]] for c in d["HarmonicConstituents"] if c["amplitude"]]


CONSTANTS = {
    "n8518750": {"kind": "harmonic", "cons": battery_cons(), "d": 0.783},
    "n8517921": {"kind": "subordinate", "ref": "n8518750", "offsets": [-18, -12, 1.03, 0.95, "R"]},
    "gNYC": {"kind": "donor", "donor": "n8518750"},
    "gDry": {"kind": "none"},
}


def rec(id_, name, path, type_="place", lat=40.7, lon=-74.0, tz="America/New_York"):
    return {"id": id_, "name": name, "path": path, "type": type_, "latitude": lat, "longitude": lon, "timezone": tz}


BATTERY = rec("n8518750", "The Battery", "us/new-york/the-battery", "gauge")
WILLIAMSBURG = rec("n8517921", "Williamsburg", "us/new-york/williamsburg", "gauge")
NYC = rec("gNYC", "New York City", "us/new-york/new-york-city")
DRY = rec("gDry", "Dry Town", "us/new-york/dry-town", lat=42.0, lon=-75.0)
COEF = {date(2026, 11, 1) + timedelta(days=k): 50 + k for k in range(31)}


def test_month_of_days_with_local_turns(sky):
    d = station_data(BATTERY, CONSTANTS["n8518750"], CONSTANTS, date(2026, 11, 14), sky, COEF)
    assert d["v"] == 1 and d["id"] == "n8518750" and d["tz"] == "America/New_York" and d["today"] == "2026-11-14"
    assert d["has_tides"] and "NOAA" in d["source"] and d["donor"] is None
    assert [x["date"] for x in d["days"]] == [f"2026-11-{k:02d}" for k in range(1, 31)]
    assert d["days"][13]["coef"] == COEF[date(2026, 11, 14)]
    a = datetime(2026, 11, 14, tzinfo=NY).astimezone(UTC)
    want = station_turns(CONSTANTS["n8518750"], CONSTANTS, a, a + timedelta(days=1))
    got = d["days"][13]["tides"]
    assert len(got) == len(want)
    for (hhmm, m, h, k), (t, hv, kind) in zip(got, want):
        local = t.astimezone(NY)
        assert m == round((t - a).total_seconds() / 60) and hhmm == f"{(local + timedelta(seconds=30)):%H:%M}"
        assert h == round(hv, 3) and k == (1 if kind == "high" else 0)
    assert d["days"][13]["sunrise"] is not None and d["days"][13]["moon"]["name"]


def test_three_day_curve_covers_a_25_hour_day(sky):
    d = station_data(BATTERY, CONSTANTS["n8518750"], CONSTANTS, date(2026, 11, 1), sky, COEF)
    c = d["curve"]
    assert c["from"] == "2026-10-31" and c["step_min"] == 10
    assert c["days"] == [1440, 1500, 1440]  # Oct 31, Nov 1 (clocks go back), Nov 2
    assert len(c["cm"]) == sum(c["days"]) // 10 + 1
    assert all(isinstance(v, int) for v in c["cm"]) and max(c["cm"]) > 50 and min(c["cm"]) < -50


def test_subordinate_curve_comes_from_its_turns(sky):
    d = station_data(WILLIAMSBURG, CONSTANTS["n8517921"], CONSTANTS, date(2026, 11, 14), sky, COEF)
    assert "offsets" in d["source"] and len(d["curve"]["cm"]) == 3 * 144 + 1
    assert all(v is not None for v in d["curve"]["cm"])


def test_donor_place_names_its_donor(sky):
    d = station_data(NYC, CONSTANTS["gNYC"], CONSTANTS, date(2026, 11, 14), sky, COEF,
                     donor={"name": "The Battery", "path": "us/new-york/the-battery"})
    assert d["donor"] == {"name": "The Battery", "path": "us/new-york/the-battery"}
    b = station_data(BATTERY, CONSTANTS["n8518750"], CONSTANTS, date(2026, 11, 14), sky, COEF)
    assert d["days"][13]["tides"] == b["days"][13]["tides"]


def test_station_without_tides_still_has_sky(sky):
    d = station_data(DRY, CONSTANTS["gDry"], CONSTANTS, date(2026, 11, 14), sky, COEF)
    assert d["has_tides"] is False and d["curve"] is None and d["source"] is None
    assert all(x["tides"] == [] for x in d["days"]) and d["days"][0]["sunrise"] is not None


def test_write_station_data_lays_out_files_by_path(tmp_path):
    cat = [BATTERY, NYC, DRY, rec("gMissing", "Missing", "us/new-york/missing")]
    constants = {"v": 1, "models": [], "stations": CONSTANTS}
    now = datetime(2026, 11, 14, 15, tzinfo=UTC)
    r = write_station_data(cat, constants, now, tmp_path, Path(os.environ.get("SKY_CACHE", ROOT / "sky-cache")))
    assert r == {"written": 4, "with_tides": 2, "sky_computed": 2}
    nyc = json.loads((tmp_path / "us/new-york/new-york-city.json").read_text(encoding="utf-8"))
    assert nyc["donor"] == {"name": "The Battery", "path": "us/new-york/the-battery"}
    assert nyc["today"] == "2026-11-14"
    missing = json.loads((tmp_path / "us/new-york/missing.json").read_text(encoding="utf-8"))
    assert missing["has_tides"] is False


def test_cli_writes_station_data(tmp_path):
    from pipeline.__main__ import main
    cat = tmp_path / "stations.json"
    cat.write_text(json.dumps([BATTERY]), encoding="utf-8")
    con = tmp_path / "tc.json"
    con.write_text(json.dumps({"v": 1, "models": [], "stations": CONSTANTS}), encoding="utf-8")
    assert main(["station-data", "--catalogue", str(cat), "--constants", str(con), "--out", str(tmp_path / "out"),
                 "--sky-cache", os.environ.get("SKY_CACHE", str(ROOT / "sky-cache")), "--now", "2026-11-14T15:00Z"]) == 0
    d = json.loads((tmp_path / "out/us/new-york/the-battery.json").read_text(encoding="utf-8"))
    assert d["today"] == "2026-11-14"


def test_sky_months_are_cached_between_runs(tmp_path, monkeypatch):
    import pipeline.station_pages as sp
    calls = []
    real = sp.sky_days
    monkeypatch.setattr(sp, "sky_days", lambda *a, **k: calls.append(a) or real(*a, **k))
    cat = [BATTERY, NYC]  # same place: one sky month
    constants = {"v": 1, "models": [], "stations": CONSTANTS}
    sky_dir = Path(os.environ.get("SKY_CACHE", ROOT / "sky-cache"))
    store = tmp_path / "sky-months"
    sp.write_station_data(cat, constants, datetime(2026, 11, 14, 15, tzinfo=UTC), tmp_path / "a", sky_dir, sky_store=store)
    assert len(calls) == 1 and (store / "2026-11.json.gz").exists()
    sp.write_station_data(cat, constants, datetime(2026, 11, 15, 15, tzinfo=UTC), tmp_path / "b", sky_dir, sky_store=store)
    assert len(calls) == 1  # the next day reuses the month
    a = json.loads((tmp_path / "a/us/new-york/the-battery.json").read_text(encoding="utf-8"))
    b = json.loads((tmp_path / "b/us/new-york/the-battery.json").read_text(encoding="utf-8"))
    assert a["days"][0]["sunrise"] == b["days"][0]["sunrise"] and b["today"] == "2026-11-15"
