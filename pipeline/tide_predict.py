"""Harmonic tide prediction (Schureman 1958, as used for NOAA's published constants).

h(t) = sum_k f_k(t) * A_k * cos(V_k(t) + u_k(t) - G_k)

A, G: amplitude (m) and Greenwich phase lag (degrees, NOAA ``phase_GMT``). V is the
equilibrium argument from the mean longitudes at t; f and u, the nodal factor and
correction, follow the 18.6-year lunar node and, as in NOAA's predictions, are held at
their value for the middle of each year (2 July 00:00 UTC). Matches NOAA's published
hourly heights at the Battery to 0.5 cm, against 1.8 cm when f and u follow t.
Heights are about the constants' own mean level (MSL for NOAA harmonic stations).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

UTC = timezone.utc
_J2000 = np.datetime64("2000-01-01T12:00:00", "s")
D2R = math.pi / 180.0


@dataclass(frozen=True)
class Constituent:
    """V = T·a + s·b + h·c + p·d + p1·e + offset (degrees); `nodal` names the f/u rule."""
    doodson: tuple[int, int, int, int, int]
    offset: float
    nodal: str


def _c(t, s, h, p, p1, off, nodal):
    return Constituent((t, s, h, p, p1), off, nodal)


# Names as NOAA spells them; EOT20/FES names map onto these in tide_model.
CONSTITUENTS: dict[str, Constituent] = {
    # semidiurnal
    "M2": _c(2, -2, 2, 0, 0, 0, "M2"), "S2": _c(2, 0, 0, 0, 0, 0, "1"), "N2": _c(2, -3, 2, 1, 0, 0, "M2"),
    "K2": _c(2, 0, 2, 0, 0, 0, "K2"), "NU2": _c(2, -3, 4, -1, 0, 0, "M2"), "MU2": _c(2, -4, 4, 0, 0, 0, "M2"),
    "2N2": _c(2, -4, 2, 2, 0, 0, "M2"), "LAM2": _c(2, -1, 0, 1, 0, 180, "M2"), "L2": _c(2, -1, 2, -1, 0, 180, "L2"),
    "T2": _c(2, 0, -1, 0, 1, 0, "1"), "R2": _c(2, 0, 1, 0, -1, 180, "1"), "2SM2": _c(2, 2, -2, 0, 0, 0, "-M2"),
    "EPS2": _c(2, -5, 4, 1, 0, 0, "M2"), "ETA2": _c(2, 1, 2, -1, 0, 0, "K2"),
    # diurnal
    "K1": _c(1, 0, 1, 0, 0, -90, "K1"), "O1": _c(1, -2, 1, 0, 0, 90, "O1"), "P1": _c(1, 0, -1, 0, 0, 90, "1"),
    "Q1": _c(1, -3, 1, 1, 0, 90, "O1"), "2Q1": _c(1, -4, 1, 2, 0, 90, "O1"), "RHO": _c(1, -3, 3, -1, 0, 90, "O1"),
    "J1": _c(1, 1, 1, -1, 0, -90, "J1"), "OO1": _c(1, 2, 1, 0, 0, -90, "OO1"), "M1": _c(1, -1, 1, 0, 0, -90, "M1"),
    "S1": _c(1, 0, 0, 0, 0, 0, "1"), "SIG1": _c(1, -4, 3, 0, 0, 90, "O1"),
    # long period
    "MM": _c(0, 1, 0, -1, 0, 0, "MM"), "MF": _c(0, 2, 0, 0, 0, 0, "MF"), "MSF": _c(0, 2, -2, 0, 0, 0, "-M2"),
    "SA": _c(0, 0, 1, 0, 0, 0, "1"), "SSA": _c(0, 0, 2, 0, 0, 0, "1"), "MSM": _c(0, 1, -2, 1, 0, 0, "MM"),
    "MTM": _c(0, 3, 0, -1, 0, 0, "MF"), "MSQM": _c(0, 4, -2, 0, 0, 0, "MF"),
    # shallow water and compounds
    "M3": _c(3, -3, 3, 0, 0, 0, "M3"), "MK3": _c(3, -2, 3, 0, 0, -90, "M2K1"), "2MK3": _c(3, -4, 3, 0, 0, 90, "M2^2/K1"),
    "M4": _c(4, -4, 4, 0, 0, 0, "M2^2"), "MN4": _c(4, -5, 4, 1, 0, 0, "M2^2"), "MS4": _c(4, -2, 2, 0, 0, 0, "M2"),
    "S4": _c(4, 0, 0, 0, 0, 0, "1"), "N4": _c(4, -6, 4, 2, 0, 0, "M2^2"),
    "M6": _c(6, -6, 6, 0, 0, 0, "M2^3"), "S6": _c(6, 0, 0, 0, 0, 0, "1"), "M8": _c(8, -8, 8, 0, 0, 0, "M2^4"),
}


def _elements(t: np.ndarray):
    """Mean longitudes in degrees at datetime64 times: T (solar hour angle), s, h, p, p1, and N."""
    sec = (t.astype("datetime64[s]") - _J2000).astype(np.float64)
    c = sec / 86400.0 / 36525.0
    s = 218.3164477 + 481267.88123421 * c
    h = 280.4664567 + 36000.76982779 * c
    p = 83.3532465 + 4069.0137287 * c
    p1 = 282.9373 + 1.71946 * c
    n = 125.04452 - 1934.136261 * c
    day_sec = (t.astype("datetime64[s]") - t.astype("datetime64[D]")).astype(np.float64)
    T = 180.0 + 15.0 * day_sec / 3600.0
    return T, s, h, p, p1, n


def _nodal(n_deg: np.ndarray, p_deg: np.ndarray) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Schureman f (factor) and u (degrees) per rule."""
    N = n_deg * D2R
    I = np.arccos(0.91370 - 0.03569 * np.cos(N))
    nu = np.arcsin(0.08893 * np.sin(N) / np.sin(I))
    xi = N - 2.0 * np.arctan(0.64412 * np.tan(N / 2.0)) - nu
    nup = np.arctan(np.sin(2 * I) * np.sin(nu) / (np.sin(2 * I) * np.cos(nu) + 0.3347))
    nupp2 = np.arctan(np.sin(I) ** 2 * np.sin(2 * nu) / (np.sin(I) ** 2 * np.cos(2 * nu) + 0.0727))
    P = p_deg * D2R - xi
    deg = 1.0 / D2R

    f_m2 = np.cos(I / 2) ** 4 / 0.9154
    u_m2 = (2 * xi - 2 * nu) * deg
    f_o1 = np.sin(I) * np.cos(I / 2) ** 2 / 0.3800
    u_o1 = (2 * xi - nu) * deg
    f_k1 = np.sqrt(0.8965 * np.sin(2 * I) ** 2 + 0.6001 * np.sin(2 * I) * np.cos(nu) + 0.1006)
    u_k1 = -nup * deg
    f_k2 = np.sqrt(19.0444 * np.sin(I) ** 4 + 2.7702 * np.sin(I) ** 2 * np.cos(2 * nu) + 0.0981)
    u_k2 = -nupp2 * deg
    tan2 = np.tan(I / 2) ** 2
    inv_ra = np.sqrt(1 - 12 * tan2 * np.cos(2 * P) + 36 * tan2 ** 2)
    r = np.arctan2(np.sin(2 * P), 1 / (6 * tan2) - np.cos(2 * P))
    q = np.arctan((5 * np.cos(I) - 1) / (7 * np.cos(I) + 1) * np.tan(P))
    inv_qa = np.sqrt(0.25 + 1.5 * np.cos(I) * np.cos(2 * P) / np.cos(I / 2) ** 2
                     + 2.25 * np.cos(I) ** 2 / np.cos(I / 2) ** 4)
    one = np.ones_like(N)
    zero = np.zeros_like(N)
    return {
        "1": (one, zero),
        "M2": (f_m2, u_m2), "-M2": (f_m2, -u_m2),
        "M2^2": (f_m2 ** 2, 2 * u_m2), "M2^3": (f_m2 ** 3, 3 * u_m2), "M2^4": (f_m2 ** 4, 4 * u_m2),
        "M3": (f_m2 ** 1.5, 1.5 * u_m2),
        "O1": (f_o1, u_o1), "K1": (f_k1, u_k1), "K2": (f_k2, u_k2),
        "J1": (np.sin(2 * I) / 0.7214, -nu * deg),
        "OO1": (np.sin(I) * np.sin(I / 2) ** 2 / 0.01640, (-2 * xi - nu) * deg),
        "M1": (f_o1 * inv_qa, u_o1 + q * deg),
        "L2": (f_m2 * inv_ra, u_m2 - r * deg),
        "MM": ((2 / 3 - np.sin(I) ** 2) / 0.5021, zero),
        "MF": (np.sin(I) ** 2 / 0.1578, -2 * xi * deg),
        "M2K1": (f_m2 * f_k1, u_m2 + u_k1),
        "M2^2/K1": (f_m2 ** 2 * f_k1, 2 * u_m2 - u_k1),
    }


def predict(times: np.ndarray, cons: list[tuple[str, float, float]]) -> np.ndarray:
    """Heights (m) at datetime64 UTC times for constituents (name, amplitude m, Greenwich phase deg)."""
    times = np.asarray(times).astype("datetime64[s]")
    T, s, h, p, p1, _ = _elements(times)
    years = times.astype("datetime64[Y]")
    mid = years.astype("datetime64[D]") + np.timedelta64(182, "D")  # 2 July (1 July in leap years: same to 1 day)
    _, _, _, p_mid, _, n_mid = _elements(mid.astype("datetime64[s]"))
    nodal = _nodal(n_mid, p_mid)
    out = np.zeros(times.shape, dtype=np.float64)
    for name, amp, phase in cons:
        c = CONSTITUENTS[name]
        a, b, cc, d, e = c.doodson
        f, u = nodal[c.nodal]
        v = a * T + b * s + cc * h + d * p + e * p1 + c.offset
        out += f * amp * np.cos((v + u - phase) * D2R)
    return out


def _dt64(t: datetime) -> np.datetime64:
    return np.datetime64(t.astimezone(UTC).replace(tzinfo=None), "s")


def _py(t: np.datetime64) -> datetime:
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(seconds=float((t - np.datetime64(0, "s")).astype(np.float64)))


MIN_GAP_H = 2.0  # turns closer than this are a ripple on a stand, not separate tides
MIN_RANGE_M = 0.01


def extrema(start: datetime, end: datetime, cons, step_min: int = 6) -> list[tuple[datetime, float, str]]:
    """High and low waters in [start, end): sampled every `step_min`, refined by a parabola."""
    pad = np.timedelta64(step_min * 60, "s")
    t0, t1 = _dt64(start) - pad, _dt64(end) + pad
    t = np.arange(t0, t1 + pad, pad)
    hh = predict(t, cons)
    d = np.diff(hh)
    idx = np.nonzero(np.sign(d[:-1]) != np.sign(d[1:]))[0] + 1
    turns = []
    step_s = step_min * 60.0
    for i in idx:
        y0, y1, y2 = hh[i - 1], hh[i], hh[i + 1]
        den = y0 - 2 * y1 + y2
        off = 0.5 * (y0 - y2) / den if den != 0 else 0.0
        ti = t[i] + np.timedelta64(int(round(off * step_s)), "s")
        turns.append([ti, None, "high" if den < 0 else "low"])
    if turns:
        hs = predict(np.array([x[0] for x in turns]), cons)
        for x, v in zip(turns, hs):
            x[1] = float(v)
    turns = _drop_ripples(turns)
    s64, e64 = _dt64(start), _dt64(end)
    return [(_py(ti), hv, k) for ti, hv, k in turns if s64 <= ti < e64]


def _drop_ripples(turns: list[list]) -> list[list]:
    """Remove adjacent high/low pairs that are too close in time or height (a stand, not a tide)."""
    changed = True
    while changed and len(turns) > 2:
        changed = False
        worst, worst_i = None, -1
        for i in range(len(turns) - 1):
            a, b = turns[i], turns[i + 1]
            gap_h = float((b[0] - a[0]).astype(np.float64)) / 3600.0
            rng = abs(b[1] - a[1])
            if gap_h < MIN_GAP_H or rng < MIN_RANGE_M:
                if worst is None or rng < worst:
                    worst, worst_i = rng, i
        if worst_i >= 0:
            del turns[worst_i:worst_i + 2]
            changed = True
    # Two of a kind in a row after removals: keep the more extreme one.
    out: list[list] = []
    for x in turns:
        if out and out[-1][2] == x[2]:
            if (x[2] == "high" and x[1] > out[-1][1]) or (x[2] == "low" and x[1] < out[-1][1]):
                out[-1] = x
        else:
            out.append(x)
    return out


# --- NOAA subordinate stations ----------------------------------------------------------------

@dataclass(frozen=True)
class Offsets:
    """NOAA tide-prediction offsets: minutes, and height ratios ("R") or additions in metres ("A")."""
    time_high_min: float
    time_low_min: float
    height_high: float
    height_low: float
    kind: str


def subordinate(ref_turns: list[tuple[datetime, float, str]], off: Offsets, ref_msl_above_mllw: float):
    """A subordinate station's turns from its reference station's (MSL heights in, MSL heights out).

    NOAA applies height offsets above MLLW. Our MSL rule: with D the reference station's MSL above
    MLLW, a ratio gives (h + D)·r − D·mean(r) and an addition h + a − mean(a), so the station's mean
    level stays at zero.
    """
    D = ref_msl_above_mllw
    mean_r = (off.height_high + off.height_low) / 2
    out = []
    for t, h, kind in ref_turns:
        high = kind == "high"
        dt = off.time_high_min if high else off.time_low_min
        v = off.height_high if high else off.height_low
        if off.kind == "R":
            hh = (h + D) * v - D * mean_r
        else:
            hh = h + v - mean_r
        out.append((t + timedelta(minutes=dt), hh, kind))
    out.sort(key=lambda x: x[0])
    return out


def curve(turns: list[tuple[datetime, float, str]], times: np.ndarray) -> np.ndarray:
    """Heights between turns by cosine interpolation (NaN outside the first and last turn)."""
    times = np.asarray(times).astype("datetime64[s]")
    tt = np.array([_dt64(t) for t, _, _ in turns]).astype("datetime64[s]").astype(np.int64)
    hh = np.array([h for _, h, _ in turns], dtype=np.float64)
    x = times.astype(np.int64)
    out = np.full(x.shape, np.nan)
    if len(tt) < 2:
        return out
    i = np.searchsorted(tt, x, side="right") - 1
    inside = (i >= 0) & (i < len(tt) - 1)
    exact_last = x == tt[-1]
    j = i[inside]
    frac = (x[inside] - tt[j]) / (tt[j + 1] - tt[j])
    out[inside] = hh[j] + (hh[j + 1] - hh[j]) * (1 - np.cos(np.pi * frac)) / 2
    out[exact_last] = hh[-1]
    return out
