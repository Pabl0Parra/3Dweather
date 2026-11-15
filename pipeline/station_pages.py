"""Daily data for every station page (spec §6 "Serving"): the calendar month of tides and sky,
and a three-day 10-minute tide curve, one file per station at ``{out}/{path}.json``.

``{"v": 1, "id", "tz", "today", "has_tides", "source", "donor": {name, path} | null,
"days": [{date, day_minutes, sunrise, ..., moon, solunar, coef, tides: [["HH:MM", minutes since
local midnight, height m, 1 high | 0 low], ...]}], "curve": {"from", "step_min", "days":
[minutes per day], "cm": [...]} | null}``
"""
from __future__ import annotations

import calendar
import json
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from .sky import load_sky, sky_days, tidal_coefficient
from .tide_predict import curve, predict
from .tide_tables import _source, station_turns

UTC = timezone.utc
STEP_MIN = 10
SKY_ROUND = 2  # stations within 0.01° (about 1 km) in the same zone share one sky computation


def _midnight(d: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(d, time(0), zone).astimezone(UTC)


def _hhmm(t: datetime, zone: ZoneInfo) -> str:
    return f"{(t + timedelta(seconds=30)).astimezone(zone):%H:%M}"


def _resolve(entry: dict, constants: dict[str, dict]) -> dict:
    return constants[entry["donor"]] if entry["kind"] == "donor" else entry


def _curve(entry: dict, constants: dict[str, dict], today: date, zone: ZoneInfo) -> dict:
    first = today - timedelta(days=1)
    edges = [_midnight(first + timedelta(days=k), zone) for k in range(4)]
    a, b = edges[0], edges[-1]
    times = np.arange(np.datetime64(a.replace(tzinfo=None), "s"), np.datetime64(b.replace(tzinfo=None), "s") + np.timedelta64(1, "s"),
                      np.timedelta64(STEP_MIN * 60, "s"))
    base = _resolve(entry, constants)
    if base["kind"] in ("harmonic", "model"):
        h = predict(times, base["cons"])
    else:
        h = curve(station_turns(entry, constants, a - timedelta(days=1), b + timedelta(days=1)), times)
    return {"from": first.isoformat(), "step_min": STEP_MIN,
            "days": [round((edges[k + 1] - edges[k]).total_seconds() / 60) for k in range(3)],
            "cm": [None if not np.isfinite(v) else int(round(v * 100)) for v in h]}


def station_data(rec: dict, entry: dict | None, constants: dict[str, dict], today: date, sky, coef: dict[date, int],
                 donor: dict | None = None, sky_month: list[dict] | None = None) -> dict:
    zone = ZoneInfo(rec["timezone"])
    first = today.replace(day=1)
    n = calendar.monthrange(first.year, first.month)[1]
    days = [dict(x) for x in (sky_month or sky_days(rec["latitude"], rec["longitude"], rec["timezone"], first, n, sky))]
    has = bool(entry) and entry["kind"] != "none"
    edges = [_midnight(first + timedelta(days=k), zone) for k in range(n + 1)]
    per_day: list[list] = [[] for _ in range(n)]
    if has:
        for t, h, kind in station_turns(entry, constants, edges[0], edges[-1]):
            i = bisect_right(edges, t) - 1
            if 0 <= i < n:
                per_day[i].append([_hhmm(t, zone), round((t - edges[i]).total_seconds() / 60), round(h, 3),
                                   1 if kind == "high" else 0])
    for k, d in enumerate(days):
        d["coef"] = coef.get(first + timedelta(days=k))
        d["tides"] = per_day[k]
    return {"v": 1, "id": rec["id"], "tz": rec["timezone"], "today": today.isoformat(), "has_tides": has,
            "source": _source(rec["id"], entry, constants) if has else None, "donor": donor if has else None,
            "days": days, "curve": _curve(entry, constants, today, zone) if has else None}


# --- whole catalogue -----------------------------------------------------------------------------

_W: dict = {}


def _init(sky_cache: str, stations: dict, coef: dict) -> None:
    _W.update(sky=load_sky(Path(sky_cache)), stations=stations, coef=coef)


def _group(job: tuple) -> int:
    (lat, lon, tz, first), items, out = job
    n = calendar.monthrange(first.year, first.month)[1]
    month = sky_days(lat, lon, tz, first, n, _W["sky"])
    for rec, today, donor in items:
        entry = _W["stations"].get(rec["id"])
        body = station_data(rec, entry, _W["stations"], today, _W["sky"], _W["coef"], donor=donor, sky_month=month)
        p = Path(out) / f"{rec['path']}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(body, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    return len(items)


def write_station_data(catalogue: list[dict], constants: dict, now: datetime, out: Path, sky_cache: Path,
                       workers: int = 1) -> dict:
    stations = constants["stations"]
    by_id = {r["id"]: r for r in catalogue}
    groups: dict[tuple, list] = defaultdict(list)
    for r in catalogue:
        today = now.astimezone(ZoneInfo(r["timezone"])).date()
        key = (round(float(r["latitude"]), SKY_ROUND), round(float(r["longitude"]), SKY_ROUND), r["timezone"],
               today.replace(day=1))
        entry = stations.get(r["id"])
        donor = None
        if entry and entry["kind"] == "donor":
            d = by_id.get(entry["donor"], {})
            donor = {"name": d.get("name"), "path": d.get("path")}
        groups[key].append((r, today, donor))
    sky = load_sky(Path(sky_cache))
    first = (now - timedelta(days=2)).date().replace(day=1)
    coef = {first + timedelta(days=k): tidal_coefficient(first + timedelta(days=k), sky) for k in range(64)}
    jobs = [(k, items, str(out)) for k, items in groups.items()]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                                 initargs=(str(sky_cache), stations, coef)) as pool:
            written = sum(pool.map(_group, jobs, chunksize=16))
    else:
        _init(str(sky_cache), stations, coef)
        written = sum(_group(j) for j in jobs)
    with_tides = sum(1 for r in catalogue if stations.get(r["id"], {}).get("kind", "none") != "none")
    return {"written": written, "with_tides": with_tides}
