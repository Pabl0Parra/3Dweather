"""Astronomical arguments and nodal corrections for the tide atlas (Schureman 1958).

Tide at a point: h(t) = sum_k f_k * A_k * cos(V_k(t) + u_k - G_k), with A and G the
atlas amplitude and Greenwich phase lag. The atlas carries f and V+u at each month
start; between month starts V advances at the constituent's speed (f and u drift
with the 18.6-year lunar node, so monthly values are close enough).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

CONSTITUENTS = ["m2", "s2", "n2", "k2", "k1", "o1", "p1", "q1"]

# Speeds in degrees per mean solar hour.
_SPEED_DEG = {"m2": 28.9841042, "s2": 30.0, "n2": 28.4397295, "k2": 30.0821373,
              "k1": 15.0410686, "o1": 13.9430356, "p1": 14.9589314, "q1": 13.3986609}
SPEEDS_RAD_PER_HOUR = [math.radians(_SPEED_DEG[c]) for c in CONSTITUENTS]

_J2000 = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)


def _arguments(t: datetime) -> tuple[float, float, float, float, float]:
    """T (mean solar hour angle), s, h, p, N in degrees at t (UTC)."""
    days = (t - _J2000).total_seconds() / 86400.0
    c = days / 36525.0
    s = 218.3164477 + 481267.88123421 * c  # Moon mean longitude
    h = 280.4664567 + 36000.76982779 * c   # Sun mean longitude
    p = 83.3532465 + 4069.0137287 * c      # lunar perigee
    n = 125.04452 - 1934.136261 * c        # lunar ascending node
    hours = t.hour + t.minute / 60 + t.second / 3600
    return 180.0 + 15.0 * hours, s, h, p, n


def nodal(t: datetime) -> dict[str, tuple[float, float]]:
    """(f, V+u in radians wrapped to -pi..pi) per constituent at t."""
    T, s, h, p, N = _arguments(t)
    n = math.radians(N)
    c1, c2, c3 = math.cos(n), math.cos(2 * n), math.cos(3 * n)
    s1, s2, s3 = math.sin(n), math.sin(2 * n), math.sin(3 * n)
    f_m2 = 1.0004 - 0.0373 * c1 + 0.0002 * c2
    u_m2 = -2.14 * s1
    f_k2 = 1.0241 + 0.2863 * c1 + 0.0083 * c2 - 0.0015 * c3
    u_k2 = -17.74 * s1 + 0.68 * s2 - 0.04 * s3
    f_k1 = 1.0060 + 0.1150 * c1 - 0.0088 * c2 + 0.0006 * c3
    u_k1 = -8.86 * s1 + 0.68 * s2 - 0.07 * s3
    f_o1 = 1.0089 + 0.1871 * c1 - 0.0147 * c2 + 0.0014 * c3
    u_o1 = 10.80 * s1 - 1.34 * s2 + 0.19 * s3
    table = {  # (f, V in degrees, u in degrees)
        "m2": (f_m2, 2 * T - 2 * s + 2 * h, u_m2),
        "s2": (1.0, 2 * T, 0.0),
        "n2": (f_m2, 2 * T - 3 * s + 2 * h + p, u_m2),
        "k2": (f_k2, 2 * T + 2 * h, u_k2),
        "k1": (f_k1, T + h - 90, u_k1),
        "o1": (f_o1, T - 2 * s + h + 90, u_o1),
        "p1": (1.0, T - h + 90, 0.0),
        "q1": (f_o1, T - 3 * s + h + p + 90, u_o1),
    }
    out = {}
    for name in CONSTITUENTS:
        f, v, u = table[name]
        out[name] = (f, (math.radians(v + u) + math.pi) % (2 * math.pi) - math.pi)
    return out


def month_starts(start: datetime, count: int) -> list[datetime]:
    out, y, m = [], start.year, start.month
    for _ in range(count):
        out.append(datetime(y, m, 1, tzinfo=timezone.utc))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out
