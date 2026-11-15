"""Sun, moon, solunar periods and the tidal coefficient, from JPL DE421 via skyfield.

Every time is given as ``["HH:MM", minutes]``: the local clock time and the minutes elapsed
since local midnight (so on a 25-hour day an event after the repeated hour has minutes =
clock + 60). An event that does not happen that day (polar day or night, a day without a
moonrise) is ``None``. Intervals are ``[from, to]`` pairs of such times, cut at the day's edges.
"""
from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

UTC = timezone.utc
# Eight 45° sectors centred on the principal phases (0° new, 90° first quarter, ...).
MOON_NAMES = ("New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous", "Full Moon",
              "Waning Gibbous", "Last Quarter", "Waning Crescent")

# Tidal coefficient (French scale): semidiurnal equilibrium amplitude of moon and sun,
# |a_m + K·a_s·e^{2iψ}|, scaled so a spring tide with both bodies on the equator at mean
# distance is 100. K = 0.357 gives mean springs/neaps of 95/45 (Brest S2/M2 ≈ 0.37). The
# astronomy is taken AGE_H hours before noon UTC; 0 matches the published French-scale
# values we checked best (the age of the tide is already in the scale's convention).
K_SUN = 0.357
AGE_H = 0.0

# Moonrise and moonset: the centre of the moon at the horizon after standard refraction (34′).
MOON_HORIZON = -0.5667
SNAP_S = 480.0  # golden/blue ends within 8 min of an exact crossing take its time
SAMPLE_MIN = 5
MOON_MEAN_KM = 385000.6
SUN_MEAN_KM = 149598023.0


@dataclass
class Sky:
    ts: object
    eph: object


def load_sky(cache: Path) -> Sky:
    """DE421 and skyfield's built-in timescale; the 17 MB ephemeris is downloaded once into ``cache``."""
    from skyfield.api import Loader
    load = Loader(str(cache), verbose=False)
    return Sky(load.timescale(builtin=True), load("de421.bsp"))


def _times(sky: Sky, t):
    return [x.replace(tzinfo=UTC) if x.tzinfo is None else x for x in t.utc_datetime()] if len(t.shape) else []


def _events(sky: Sky, finder, *args, keep=None):
    t, y = finder(*args)
    out = _times(sky, t)
    if keep is not None:
        return [x for x, ok in zip(out, y) if ok]
    return out


def sky_days(lat: float, lon: float, tz: str, first: date, n: int, sky: Sky) -> list[dict]:
    from skyfield import almanac
    from skyfield.api import wgs84
    from skyfield.nutationlib import iau2000b_radians

    zone = ZoneInfo(tz)
    days = [first + timedelta(days=k) for k in range(n + 1)]
    edges = [datetime.combine(d, time(0), zone).astimezone(UTC) for d in days]
    ts, eph = sky.ts, sky.eph
    earth, sun, moon = eph["earth"], eph["sun"], eph["moon"]
    obs = earth + wgs84.latlon(lat, lon)
    anti = earth + wgs84.latlon(lat, ((lon + 360.0) % 360.0) - 180.0)
    pad = timedelta(hours=26)
    t0, t1 = ts.from_datetime(edges[0] - pad), ts.from_datetime(edges[-1] + pad)

    def rising(body, h=None):
        return _events(sky, almanac.find_risings, obs, body, t0, t1, *([] if h is None else [h]), keep=True)

    def setting(body, h=None):
        return _events(sky, almanac.find_settings, obs, body, t0, t1, *([] if h is None else [h]), keep=True)

    sunrise, sunset = rising(sun), setting(sun)
    up = {h: rising(sun, h) for h in (-6.0, -4.0, 6.0)}
    down = {h: setting(sun, h) for h in (-6.0, -4.0, 6.0)}
    sun_transit = _times(sky, almanac.find_transits(obs, sun, t0, t1))
    moonrise, moonset = rising(moon, MOON_HORIZON), setting(moon, MOON_HORIZON)
    moon_transit = _times(sky, almanac.find_transits(obs, moon, t0, t1))
    moon_anti = _times(sky, almanac.find_transits(anti, moon, t0, t1))

    # Golden (-4°..6°) and blue (-6°..-4°) hours: runs of SAMPLE_MIN-minute altitude samples inside each
    # band, so a sun that never leaves a band (polar winter, white nights) gives one long run.
    # Each end snaps to the exact crossing found above when there is one within SNAP.
    step = SAMPLE_MIN / 1440.0
    start_t = ts.from_datetime(edges[0])
    n_samp = int(round((edges[-1] - edges[0]).total_seconds() / (60.0 * SAMPLE_MIN))) + 1
    grid = ts.tt_jd(start_t.tt + np.arange(n_samp) * step)
    grid._nutation_angles_radians = iau2000b_radians(grid)  # 1 mas series: thousands of times, cheaply
    alt = obs.at(grid).observe(sun).apparent().altaz()[0].degrees
    sample_t = [edges[0] + timedelta(minutes=SAMPLE_MIN * k) for k in range(n_samp)]
    crossings = {h: sorted(up[h] + down[h]) for h in (-6.0, -4.0, 6.0)}

    def band(lo: float, hi: float) -> list[tuple[datetime, datetime]]:
        inside = (alt >= lo) & (alt < hi)
        runs, k = [], 0
        while k < n_samp:
            if not inside[k]:
                k += 1
                continue
            j = k
            while j + 1 < n_samp and inside[j + 1]:
                j += 1
            runs.append((_cross(k - 1, k, lo, hi) if k > 0 else sample_t[0],
                         _cross(j, j + 1, lo, hi) if j + 1 < n_samp else sample_t[-1]))
            k = j + 1
        return runs

    def _cross(i: int, j: int, lo: float, hi: float) -> datetime:
        """Time the altitude crosses lo or hi between samples i and j (exact event if close)."""
        h = lo if min(alt[i], alt[j]) < lo <= max(alt[i], alt[j]) else hi
        w = (h - alt[i]) / (alt[j] - alt[i]) if alt[j] != alt[i] else 0.0
        guess = sample_t[i] + timedelta(minutes=SAMPLE_MIN * float(w))
        ev = crossings[h]
        k = bisect_left(ev, guess)
        near = [e for e in ev[max(0, k - 1):k + 1] if abs((e - guess).total_seconds()) <= SNAP_S]
        return min(near, key=lambda e: abs((e - guess).total_seconds())) if near else guess

    golden_runs, blue_runs = band(-4.0, 6.0), band(-6.0, -4.0)

    # Is the sun up at each local midnight (for the length of day)?
    mid = ts.from_datetimes(edges)
    alt0 = obs.at(mid).observe(sun).apparent().altaz()[0].degrees
    noons = ts.from_datetimes([e + (edges[i + 1] - e) / 2 for i, e in enumerate(edges[:-1])])
    phase_deg = almanac.moon_phase(eph, noons).degrees
    geo_moon = earth.at(noons).observe(moon).apparent()
    illum = geo_moon.fraction_illuminated(sun) * 100.0
    dist = geo_moon.distance().km

    out = []
    for i, d in enumerate(days[:-1]):
        a, b = edges[i], edges[i + 1]
        span = round((b - a).total_seconds() / 60)

        def at(x: datetime) -> list:
            x = (x + timedelta(seconds=30)).replace(second=0, microsecond=0)  # nearest minute
            loc = x.astimezone(zone)
            return [f"{loc.hour:02d}:{loc.minute:02d}", min(span, max(0, round((x - a).total_seconds() / 60)))]

        def first_in(xs):
            k = bisect_left(xs, a)
            return at(xs[k]) if k < len(xs) and xs[k] < b else None

        def within(runs):
            res = []
            for s0, e0 in runs:
                if e0 > a and s0 < b:
                    x, y = at(max(s0, a)), at(min(e0, b))
                    if y[1] > x[1]:
                        res.append([x, y])
            return res

        def around(xs, half_min):
            h = timedelta(minutes=half_min)
            return [[at(max(x - h, a)), at(min(x + h, b))] for x in xs if a <= x < b]

        rise, sett = first_in(sunrise), first_in(sunset)
        # Minutes the sun is above the horizon between the edges.
        flips = sorted([(x, True) for x in sunrise if a <= x < b] + [(x, False) for x in sunset if a <= x < b])
        is_up, last, above = bool(alt0[i] > -0.8333), a, 0.0
        for x, now_up in flips:
            if is_up:
                above += (x - last).total_seconds()
            is_up, last = now_up, x
        if is_up:
            above += (b - last).total_seconds()

        name = MOON_NAMES[int(((float(phase_deg[i]) % 360.0) + 22.5) // 45) % 8]
        out.append({
            "date": d.isoformat(),
            "day_minutes": span,
            "sunrise": rise, "sunset": sett, "transit": first_in(sun_transit),
            "dawn": first_in(up[-6.0]), "dusk": first_in(down[-6.0]),
            "golden": within(golden_runs),
            "blue": within(blue_runs),
            "day_length_h": round(above / 3600.0, 2),
            "moon": {
                "phase_angle": round(float(phase_deg[i]) % 360.0, 1),
                "illum": int(round(float(illum[i]))),
                "name": name,
                "rise": first_in(moonrise), "set": first_in(moonset), "transit": first_in(moon_transit),
                "distance_km": int(round(float(dist[i]))),
            },
            "solunar": {
                "major": sorted(around(moon_transit, 60) + around(moon_anti, 60), key=lambda p: p[0][1]),
                "minor": sorted(around(moonrise, 30) + around(moonset, 30), key=lambda p: p[0][1]),
            },
        })
    return out


def tidal_coefficient(day: date, sky: Sky) -> int:
    """French-scale coefficient (20-120) for ``day``, from the moon's and sun's declination and distance."""
    t = sky.ts.from_datetime(datetime.combine(day, time(12), UTC) - timedelta(hours=AGE_H))
    earth = sky.eph["earth"].at(t)
    terms = []
    for body, mean_km in ((sky.eph["moon"], MOON_MEAN_KM), (sky.eph["sun"], SUN_MEAN_KM)):
        ra, dec, d = earth.observe(body).apparent().radec(epoch="date")
        terms.append(((mean_km / d.km) ** 3 * math.cos(dec.radians) ** 2, ra.radians))
    (am, ram), (as_, ras) = terms
    amp = abs(am + K_SUN * as_ * np.exp(2j * (ras - ram)))
    return int(min(120, max(20, round(100.0 * amp / (1.0 + K_SUN)))))
