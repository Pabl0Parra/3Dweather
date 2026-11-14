"""Nodal factors and astronomical arguments for the tide atlas's 8 constituents.

Oracle: the published monthly (f, V0+u) values of the reference site's atlas for
2026-01, 2026-07 and 2035-12 (physics, not code); ours are computed from the
standard Schureman formulas.
"""
import math
from datetime import datetime, timezone

import pytest

from pipeline.tide_astro import CONSTITUENTS, SPEEDS_RAD_PER_HOUR, month_starts, nodal

ORACLE = {
    (2026, 1): [0.96497, 1.152665, 1.0, 0.0, 0.96497, 1.036081, 1.301467, -2.681765, 1.108729, 0.227452,
                1.176054, 0.908705, 1.0, -0.186178, 1.176054, 0.79212],
    (2026, 7): [0.967327, -0.465589, 1.0, 0.0, 0.967327, 2.12721, 1.28174, -2.692731, 1.103173, -2.92074,
                1.166918, 2.429975, 1.0, 2.983302, 1.166918, -1.260411],
    (2035, 12): [1.032882, -0.367738, 1.0, 0.0, 1.032882, -3.073351, 0.777775, 2.27114, 0.901604, -0.442316,
                 0.838872, 0.122058, 1.0, 0.354365, 0.838872, -2.583556],
}


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def test_constituents_and_speeds():
    assert CONSTITUENTS == ["m2", "s2", "n2", "k2", "k1", "o1", "p1", "q1"]
    deg_per_hour = [28.9841042, 30.0, 28.4397295, 30.0821373, 15.0410686, 13.9430356, 14.9589314, 13.3986609]
    for got, want in zip(SPEEDS_RAD_PER_HOUR, deg_per_hour):
        assert got == pytest.approx(math.radians(want), abs=1e-9)


@pytest.mark.parametrize("ym", sorted(ORACLE))
def test_nodal_matches_published_values(ym):
    t = datetime(ym[0], ym[1], 1, tzinfo=timezone.utc)
    got = nodal(t)
    want = ORACLE[ym]
    for k, name in enumerate(CONSTITUENTS):
        f, phase = got[name]
        assert f == pytest.approx(want[2 * k], abs=0.002), name
        assert abs(wrap(phase - want[2 * k + 1])) < math.radians(0.5), name  # within half a degree


def test_month_starts():
    m = month_starts(datetime(2026, 1, 1, tzinfo=timezone.utc), 14)
    assert len(m) == 14 and m[0] == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert m[12] == datetime(2027, 1, 1, tzinfo=timezone.utc) and m[13] == datetime(2027, 2, 1, tzinfo=timezone.utc)
