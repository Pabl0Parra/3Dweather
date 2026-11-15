import gzip
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipeline.tide_predict import Offsets, extrema, subordinate
from pipeline.tide_tables import station_turns, table_window, write_tables

FIX = Path(__file__).parent / "fixtures" / "noaa"
UTC = timezone.utc


def battery_cons():
    d = json.loads((FIX / "8518750-harcon.json").read_text(encoding="utf-8"))
    return [[c["name"], c["amplitude"], c["phase_GMT"]] for c in d["HarmonicConstituents"] if c["amplitude"]]


D = 0.783
WILLIAMSBURG = [-18, -12, 1.03, 0.95, "R"]


def constants():
    cons = battery_cons()
    return {
        "v": 1, "models": ["EOT20 test"],
        "stations": {
            "n8518750": {"kind": "harmonic", "cons": cons, "d": D},
            "n8517921": {"kind": "subordinate", "ref": "n8518750", "offsets": WILLIAMSBURG},
            "gNYC": {"kind": "donor", "donor": "n8518750"},
            "gSea": {"kind": "model", "cons": [["M2", 0.5, 30.0], ["K1", 0.1, 100.0]], "source": "EOT20 test"},
            "gDry": {"kind": "none"},
        },
    }


def rec(id_, name, path, type_="place"):
    return {"id": id_, "name": name, "path": path, "type": type_, "latitude": 40.7, "longitude": -74.0}


CATALOGUE = [
    rec("n8518750", "The Battery", "us/new-york/the-battery", "gauge"),
    rec("n8517921", "Williamsburg", "us/new-york/williamsburg", "gauge"),
    rec("gNYC", "New York City", "us/new-york/new-york-city"),
    rec("gSea", "Sea Town", "xx/sea/sea-town"),
    rec("gDry", "Dry Town", "xx/land/dry-town"),
]


def test_window_is_12_months_either_side_of_the_run_month():
    assert table_window(date(2026, 11, 14)) == (datetime(2025, 11, 1, tzinfo=UTC), datetime(2027, 12, 1, tzinfo=UTC))
    assert table_window(date(2026, 1, 1)) == (datetime(2025, 1, 1, tzinfo=UTC), datetime(2027, 2, 1, tzinfo=UTC))


def test_station_turns_follow_each_kind():
    c = constants()["stations"]
    a, b = datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 8, tzinfo=UTC)
    harmonic = station_turns(c["n8518750"], c, a, b)
    assert harmonic == extrema(a, b, battery_cons())
    assert station_turns(c["gNYC"], c, a, b) == harmonic
    want = subordinate(extrema(a - timedelta(hours=6), b + timedelta(hours=6), battery_cons()), Offsets(*WILLIAMSBURG), D)
    want = [x for x in want if a <= x[0] < b]
    assert station_turns(c["n8517921"], c, a, b) == want
    assert station_turns(c["gDry"], c, a, b) == []


def test_write_tables(tmp_path):
    out = tmp_path / "tides"
    summary = write_tables(CATALOGUE, constants(), date(2026, 11, 14), out)
    assert summary == {"written": 4, "without": 1}
    bat = json.loads((out / "us/new-york/the-battery.json").read_text(encoding="utf-8"))
    assert bat["v"] == 1 and bat["id"] == "n8518750" and bat["datum"] == "MSL" and bat["donor"] is None
    assert bat["from"] == "2025-11-01T00:00:00Z" and bat["to"] == "2027-12-01T00:00:00Z"
    assert "NOAA" in bat["source"] and "8518750" in bat["source"]
    turns = bat["turns"]
    assert turns[0][0] < 13 * 60 and turns[-1][0] > (datetime(2027, 12, 1) - datetime(2025, 11, 1)).total_seconds() / 60 - 13 * 60
    assert all(isinstance(m, int) and isinstance(h, int) and k in (0, 1) for m, h, k in turns)  # whole minutes and cm
    # Same turns as the engine, rounded.
    a = datetime(2025, 11, 1, tzinfo=UTC)
    first = extrema(a, a + timedelta(days=2), battery_cons())
    for (m, h, k), (t, hv, kind) in zip(turns, first):
        assert m == round((t - a).total_seconds() / 60) and h == round(hv * 100) and k == (1 if kind == "high" else 0)
    assert len(gzip.compress(json.dumps(bat, separators=(",", ":")).encode())) < 40_000

    nyc = json.loads((out / "us/new-york/new-york-city.json").read_text(encoding="utf-8"))
    assert nyc["id"] == "gNYC" and nyc["turns"] == bat["turns"]
    assert nyc["donor"] == {"name": "The Battery", "path": "us/new-york/the-battery"}
    sub = json.loads((out / "us/new-york/williamsburg.json").read_text(encoding="utf-8"))
    assert "offsets" in sub["source"] and "8518750" in sub["source"]
    sea = json.loads((out / "xx/sea/sea-town.json").read_text(encoding="utf-8"))
    assert sea["source"] == "EOT20 test"
    assert not (out / "xx/land/dry-town.json").exists()
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index["without"] == ["gDry"] and index["from"] == bat["from"] and index["models"] == ["EOT20 test"]


def test_a_station_missing_from_the_constants_gets_no_file(tmp_path):
    summary = write_tables([rec("gNew", "New", "xx/new/new")], {"v": 1, "models": [], "stations": {}},
                           date(2026, 11, 1), tmp_path)
    assert summary == {"written": 0, "without": 1}


def test_worker_processes_write_the_same_files(tmp_path):
    write_tables(CATALOGUE, constants(), date(2026, 11, 14), tmp_path / "one")
    write_tables(CATALOGUE, constants(), date(2026, 11, 14), tmp_path / "two", workers=2)
    for p in (tmp_path / "one").rglob("*.json"):
        assert p.read_text(encoding="utf-8") == (tmp_path / "two" / p.relative_to(tmp_path / "one")).read_text(encoding="utf-8")


def test_cli_builds_tables_for_a_month(tmp_path):
    from pipeline.__main__ import main
    cat = tmp_path / "stations.json"
    cat.write_text(json.dumps(CATALOGUE), encoding="utf-8")
    con = tmp_path / "tide-constants.json"
    con.write_text(json.dumps(constants()), encoding="utf-8")
    assert main(["tide-tables", "--catalogue", str(cat), "--constants", str(con), "--month", "2026-11",
                 "--out", str(tmp_path / "tides")]) == 0
    assert json.loads((tmp_path / "tides" / "index.json").read_text(encoding="utf-8"))["from"] == "2025-11-01T00:00:00Z"


REF = Path(__file__).parent.parent / "reference" / "thetidechart-capture" / "pages" / "station.html"
BUILT = Path(__file__).parent.parent / "tide-out" / "tide-constants.json"


@pytest.mark.reference
@pytest.mark.skipif(not (REF.exists() and BUILT.exists()), reason="needs the capture and a local tide-constants.json")
def test_new_york_city_matches_the_capture():
    """Spec §9: within 2 min and 2 cm. The reference uses FES2022 at the place, so this runs only on FES constants."""
    import re
    built = json.loads(BUILT.read_text(encoding="utf-8"))
    entry = built["stations"].get("g5128581")
    if not entry or not str(entry.get("source", "")).startswith("FES2022"):
        pytest.skip(f"New York City is on {entry and (entry.get('source') or entry['kind'])}, not FES2022")
    ref = json.loads(re.search(r'id="tc-data"[^>]*>(.*?)</script>', REF.read_text(encoding="utf-8"), re.S).group(1))
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(ref["tz"])
    want = []
    for day in ref["days"]:
        for x in day["tides"]:
            local = datetime.fromisoformat(f"{day['date']}T{x['t']}").replace(tzinfo=tz)
            want.append((local.astimezone(UTC), x["h"], x["type"]))
    a, b = want[0][0] - timedelta(hours=1), want[-1][0] + timedelta(hours=1)
    got = station_turns(entry, built["stations"], a, b)
    assert len(got) == len(want)
    for (t, h, k), (wt, wh, wk) in zip(got, want):
        assert k == wk and abs((t - wt).total_seconds()) <= 120 + 59 and abs(h - wh) <= 0.02
