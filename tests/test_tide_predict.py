import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from pipeline.tide_predict import CONSTITUENTS, extrema, predict

FIX = Path(__file__).parent / "fixtures" / "noaa"
UTC = timezone.utc


def battery():
    d = json.loads((FIX / "8518750-harcon.json").read_text(encoding="utf-8"))
    return [(c["name"], c["amplitude"], c["phase_GMT"]) for c in d["HarmonicConstituents"]]


def noaa(name):
    rows = json.loads((FIX / name).read_text(encoding="utf-8"))["predictions"]
    return [(datetime.strptime(r["t"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC), float(r["v"]), r.get("type")) for r in rows]


def t64(ts):
    return np.array([np.datetime64(t.replace(tzinfo=None), "s") for t in ts])


def test_every_noaa_constituent_is_known():
    names = [c[0] for c in battery()]
    assert len(names) == 37
    assert all(n in CONSTITUENTS for n in names)


def test_hourly_heights_match_noaa():
    rows = noaa("8518750-hourly-2026-11-01.json")
    h = predict(t64([r[0] for r in rows]), battery())
    diff = np.abs(h - np.array([r[1] for r in rows]))
    assert len(rows) == 72
    assert diff.max() <= 0.01, diff.max()


def test_turns_match_noaa_hilo():
    want = noaa("8518750-hilo-2026-11.json")
    got = extrema(datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 12, 1, tzinfo=UTC), battery())
    assert len(got) == len(want)
    for (t, h, kind), (wt, wh, wk) in zip(got, want):
        assert kind == ("high" if wk == "H" else "low")
        assert abs((t - wt).total_seconds()) <= 120, (t, wt)
        assert abs(h - wh) <= 0.01, (t, h, wh)


def test_unknown_constituent_is_an_error():
    with pytest.raises(KeyError, match="XYZ9"):
        predict(t64([datetime(2026, 1, 1, tzinfo=UTC)]), [("XYZ9", 1.0, 0.0)])


def test_double_high_ripple_is_not_two_turns():
    # M2 with a strong M4/M6 shoulder: a flat stand near high water, but only real turns, at least 2 h apart.
    cons = [("M2", 1.0, 0.0), ("M4", 0.18, 250.0), ("M6", 0.05, 30.0)]
    start = datetime(2026, 3, 1, tzinfo=UTC)
    turns = extrema(start, start + timedelta(days=3), cons)
    kinds = [k for _, _, k in turns]
    assert all(a != b for a, b in zip(kinds, kinds[1:]))  # alternate high/low
    gaps = [(b[0] - a[0]).total_seconds() / 3600 for a, b in zip(turns, turns[1:])]
    assert min(gaps) >= 2.0
    # Each turn really is a local extreme of the curve.
    for t, h, k in turns:
        around = predict(t64([t - timedelta(minutes=10), t + timedelta(minutes=10)]), cons)
        assert (h >= around.max() - 1e-4) if k == "high" else (h <= around.min() + 1e-4)


def test_extrema_heights_equal_predict():
    cons = battery()
    turns = extrema(datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 3, tzinfo=UTC), cons)
    h = predict(t64([t for t, _, _ in turns]), cons)
    assert np.allclose(h, [x[1] for x in turns], atol=1e-6)


# --- Task 2: subordinate stations and curves -------------------------------------------------

from pipeline.tide_predict import Offsets, curve, subordinate  # noqa: E402


def williamsburg_offsets():
    o = json.loads((FIX / "8517921-offsets.json").read_text(encoding="utf-8"))
    return Offsets(o["timeOffsetHighTide"], o["timeOffsetLowTide"], o["heightOffsetHighTide"],
                   o["heightOffsetLowTide"], o["heightAdjustedType"])


def battery_d():
    d = {x["name"]: x["value"] for x in json.loads((FIX / "8518750-datums.json").read_text(encoding="utf-8"))["datums"]}
    return d["MSL"] - d["MLLW"]


def test_subordinate_matches_noaa_on_mllw():
    D = battery_d()
    ref = extrema(datetime(2026, 10, 31, tzinfo=UTC), datetime(2026, 12, 2, tzinfo=UTC), battery())
    ref_mllw = [(t, h + D, k) for t, h, k in ref]
    got = subordinate(ref_mllw, williamsburg_offsets(), 0.0)  # D = 0: heights stay on MLLW
    want = noaa("8517921-hilo-mllw-2026-11.json")
    got = [x for x in got if want[0][0] - timedelta(minutes=5) <= x[0] <= want[-1][0] + timedelta(minutes=5)]
    assert len(got) == len(want)
    for (t, h, k), (wt, wh, wk) in zip(got, want):
        assert k == ("high" if wk == "H" else "low")
        assert abs((t - wt).total_seconds()) <= 60 + 59, (t, wt)  # NOAA rounds to the minute
        assert abs(h - wh) <= 0.01, (t, h, wh)


def test_subordinate_msl_heights():
    t0 = datetime(2026, 11, 1, tzinfo=UTC)
    ref = [(t0, 0.6, "high"), (t0 + timedelta(hours=6), -0.5, "low")]
    ratio = subordinate(ref, Offsets(-18, -12, 1.10, 0.90, "R"), 0.8)
    # (h + D)·r − D·(r_high + r_low)/2, with D = 0.8 and mean ratio 1.0
    assert ratio[0][1] == pytest.approx((0.6 + 0.8) * 1.10 - 0.8)
    assert ratio[1][1] == pytest.approx((-0.5 + 0.8) * 0.90 - 0.8)
    assert ratio[0][0] == t0 - timedelta(minutes=18) and ratio[1][0] == t0 + timedelta(hours=6, minutes=-12)
    add = subordinate(ref, Offsets(5, 10, 0.3, 0.1, "A"), 0.8)
    assert add[0][1] == pytest.approx(0.6 + 0.3 - 0.2) and add[1][1] == pytest.approx(-0.5 + 0.1 - 0.2)


def test_subordinate_keeps_order_when_offsets_cross():
    t0 = datetime(2026, 11, 1, tzinfo=UTC)
    ref = [(t0, 1.0, "high"), (t0 + timedelta(hours=1), 0.9, "low"), (t0 + timedelta(hours=7), 1.0, "high")]
    out = subordinate(ref, Offsets(90, -40, 1.0, 1.0, "R"), 0.0)
    assert [x[0] for x in out] == sorted(x[0] for x in out)


def test_curve_passes_through_turns_and_is_monotonic_between():
    turns = extrema(datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 3, tzinfo=UTC), battery())
    pts = t64([t for t, _, _ in turns])
    assert np.allclose(curve(turns, pts), [h for _, h, _ in turns], atol=1e-9)
    a, b = turns[0], turns[1]
    span = np.arange(pts[0], pts[1], np.timedelta64(600, "s"))
    c = curve(turns, span)
    assert np.all(np.diff(c) <= 1e-12) if a[2] == "high" else np.all(np.diff(c) >= -1e-12)
    outside = curve(turns, t64([turns[0][0] - timedelta(hours=1)]))
    assert np.isnan(outside[0])


def test_additive_subordinate_matches_noaa_on_mllw():
    """9414539 from 9414290 with additive ("F") offsets, as NOAA gives them with units=metric."""
    o = json.loads((FIX / "9414539-offsets-metric.json").read_text(encoding="utf-8"))
    h = json.loads((FIX / "9414290-harcon.json").read_text(encoding="utf-8"))
    cons = [(c["name"], c["amplitude"], c["phase_GMT"]) for c in h["HarmonicConstituents"] if c["amplitude"]]
    dat = {x["name"]: x["value"] for x in json.loads((FIX / "9414290-datums.json").read_text(encoding="utf-8"))["datums"]}
    D = dat["MSL"] - dat["MLLW"]
    ref = extrema(datetime(2026, 10, 31, tzinfo=UTC), datetime(2026, 11, 4, tzinfo=UTC), cons)
    off = Offsets(o["timeOffsetHighTide"], o["timeOffsetLowTide"], o["heightOffsetHighTide"], o["heightOffsetLowTide"],
                  o["heightAdjustedType"])
    mean_a = (off.height_high + off.height_low) / 2  # our MSL rule removes it; NOAA's MLLW heights keep it
    got = [(t, x + mean_a, k) for t, x, k in subordinate([(t, x + D, k) for t, x, k in ref], off, 0.0)]
    want = noaa("9414539-hilo-mllw-2026-11-01.json")
    got = [x for x in got if want[0][0] - timedelta(minutes=5) <= x[0] <= want[-1][0] + timedelta(minutes=5)]
    assert len(got) == len(want)
    for (t, hv, k), (wt, wh, wk) in zip(got, want):
        assert k == ("high" if wk == "H" else "low")
        assert abs((t - wt).total_seconds()) <= 119 and abs(hv - wh) <= 0.02, (t, hv, wt, wh)
