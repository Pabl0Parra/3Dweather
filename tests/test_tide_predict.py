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
