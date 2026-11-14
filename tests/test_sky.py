import json
import os
import re
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("skyfield")

from pipeline.sky import load_sky, sky_days, tidal_coefficient  # noqa: E402

ROOT = Path(__file__).parent.parent
CAPTURE = ROOT / "reference" / "thetidechart-capture" / "pages" / "station.html"
NYC = (40.71427, -74.00597, "America/New_York")
TROMSO = (69.6492, 18.9553, "Europe/Oslo")


@pytest.fixture(scope="module")
def sky():
    return load_sky(Path(os.environ.get("SKY_CACHE", ROOT / "sky-cache")))


def mins(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def test_polar_night_and_midnight_sun_are_null(sky):
    dec = sky_days(*TROMSO, date(2026, 12, 15), 1, sky)[0]
    assert dec["sunrise"] is None and dec["sunset"] is None and dec["day_length_h"] == 0
    assert dec["dawn"] is not None  # civil twilight still happens at noon
    jun = sky_days(*TROMSO, date(2026, 6, 21), 1, sky)[0]
    assert jun["sunrise"] is None and jun["sunset"] is None and jun["day_length_h"] == 24
    assert jun["dawn"] is None and jun["dusk"] is None and jun["golden"] == [] and jun["blue"] == []


def test_dst_end_day_is_25_hours_and_times_are_local(sky):
    day, nxt = sky_days(*NYC, date(2026, 11, 1), 2, sky)
    assert day["date"] == "2026-11-01" and day["day_minutes"] == 1500 and nxt["day_minutes"] == 1440
    t, m = day["sunrise"]
    assert "06:15" <= t <= "06:35"  # standard time, after the 02:00 change
    assert m == mins(t) + 60  # minutes elapsed since local midnight count the repeated hour
    t, m = nxt["sunrise"]
    assert m == mins(t)


def test_solunar_periods_are_centred_on_moon_events(sky):
    d = sky_days(*NYC, date(2026, 11, 13), 1, sky)[0]
    for (a, b) in d["solunar"]["major"]:
        assert b[1] - a[1] == 120 or a[1] == 0 or b[1] == d["day_minutes"]  # cut at the day's edges
    centres = [(a[1] + b[1]) / 2 for a, b in d["solunar"]["major"] if b[1] - a[1] == 120]
    assert any(abs(c - d["moon"]["transit"][1]) <= 0.5 for c in centres)
    minors = {(a[1] + b[1]) / 2 for a, b in d["solunar"]["minor"] if b[1] - a[1] == 60}
    assert any(abs(c - d["moon"]["rise"][1]) <= 0.5 for c in minors)
    assert any(abs(c - d["moon"]["set"][1]) <= 0.5 for c in minors)


def test_golden_and_blue_hours_meet(sky):
    d = sky_days(*NYC, date(2026, 11, 13), 1, sky)[0]
    (bm, gm), (ge, be) = (d["blue"][0], d["golden"][0]), (d["golden"][1], d["blue"][1])
    assert bm[1] == gm[0] and ge[1] == be[0]  # blue (-6..-4°) runs into golden (-4..+6°)
    assert d["dawn"][1] == bm[0][1] and d["dusk"][1] == be[1][1]
    assert gm[0][1] < d["sunrise"][1] < gm[1][1] and ge[0][1] < d["sunset"][1] < ge[1][1]
    assert 9.9 < d["day_length_h"] < 10.1


def test_coefficient_range_and_equinox_springs(sky):
    year = [(date(2026, 1, 1).toordinal() + k) for k in range(365)]
    coef = {date.fromordinal(o): tidal_coefficient(date.fromordinal(o), sky) for o in year}
    assert all(20 <= c <= 120 for c in coef.values())
    assert max(coef.values()) >= 100 and min(coef.values()) <= 35
    top = sorted(coef, key=coef.get)[-6:]
    assert all(d.month in (1, 2, 3, 4, 8, 9, 10, 11, 12) for d in top)  # not midsummer
    assert max(coef.values()) in [coef[d] for d in coef if d.month in (2, 3, 4, 8, 9, 10)]


def test_moon_names_are_45_degree_sectors_around_the_principal_phases(sky):
    names = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous", "Full Moon",
             "Waning Gibbous", "Last Quarter", "Waning Crescent"]
    for d in sky_days(*NYC, date(2026, 11, 1), 30, sky):
        p = d["moon"]["phase_angle"]
        assert d["moon"]["name"] == names[int((p + 22.5) // 45) % 8], (d["date"], p)
        assert 0 <= d["moon"]["illum"] <= 100 and 356000 < d["moon"]["distance_km"] < 407000


@pytest.mark.reference
@pytest.mark.skipif(not CAPTURE.exists(), reason="needs the local reference capture")
def test_new_york_matches_the_capture(sky):
    html = CAPTURE.read_text(encoding="utf-8")
    ref = json.loads(re.search(r'id="tc-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    lat, lon, tz = ref["lat"], ref["lon"], ref["tz"]
    want = ref["days"]
    got = sky_days(lat, lon, tz, date.fromisoformat(want[0]["date"]), len(want), sky)
    worst = {"sun": 0, "moon": 0, "illum": 0, "coef": 0}
    for g, w in zip(got, want):
        assert g["date"] == w["date"]
        for k in ("sunrise", "sunset"):
            worst["sun"] = max(worst["sun"], abs(mins(g[k][0]) - mins(w[k])))
        for k in ("rise", "set"):
            if w["moon"].get(k):
                worst["moon"] = max(worst["moon"], abs(mins(g["moon"][k][0]) - mins(w["moon"][k])))
            else:
                assert g["moon"][k] is None
        worst["illum"] = max(worst["illum"], abs(g["moon"]["illum"] - w["moon"]["illum"]))
        assert g["moon"]["name"].lower() == w["moon"]["name"].lower(), (g["date"], g["moon"]["name"], w["moon"]["name"])
        worst["coef"] = max(worst["coef"], abs(tidal_coefficient(date.fromisoformat(w["date"]), sky) - w["coef"]))
    print("worst differences:", worst)
    assert worst["sun"] <= 1 and worst["moon"] <= 2 and worst["illum"] <= 1
    assert worst["coef"] <= 8
