"""Daily data for every station page (spec §6 "Serving"): the calendar month of tides and sky,
and a three-day 10-minute tide curve, one file per station at ``{out}/{path}.json``.

``{"v": 1, "id", "tz", "today", "has_tides", "source", "donor": {name, path} | null,
"days": [{date, day_minutes, sunrise, ..., moon, solunar, coef, tides: [["HH:MM", minutes since
local midnight, height m, 1 high | 0 low], ...]}], "curve": {"from", "step_min", "days":
[minutes per day], "cm": [...]} | null}``
"""
from __future__ import annotations

import calendar
import gzip
import json
from bisect import bisect_right
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
# Pass 1 computes each sky month once (it is the same every day of the month, so months are kept
# in ``sky_store`` between daily runs as {YYYY-MM}.json.gz); pass 2 writes the station files.

_W: dict = {}


def _init(sky_cache: str, stations: dict, coef: dict) -> None:
    _W.update(sky=load_sky(Path(sky_cache)), stations=stations, coef=coef)


def _sky_job(key: tuple) -> tuple:
    lat, lon, tz, first = key
    n = calendar.monthrange(first.year, first.month)[1]
    return key, sky_days(lat, lon, tz, first, n, _W["sky"])


def _write_job(job: tuple) -> int:
    items, out = job  # each item carries its own sky month: workers never hold the whole set
    for rec, today, donor, month in items:
        entry = _W["stations"].get(rec["id"])
        body = station_data(rec, entry, _W["stations"], today, _W["sky"], _W["coef"], donor=donor,
                            sky_month=month)
        p = Path(out) / f"{rec['path']}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(body, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    return len(items)


def _key_text(key: tuple) -> str:
    lat, lon, tz, first = key
    return f"{lat}|{lon}|{tz}"


def _load_months(store: Path | None, first: date) -> dict[str, list]:
    if store is None:
        return {}
    p = Path(store) / f"{first:%Y-%m}.json.gz"
    if not p.exists():
        return {}
    try:
        return json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))
    except (OSError, ValueError):
        return {}


def _save_months(store: Path, first: date, months: dict[str, list]) -> None:
    Path(store).mkdir(parents=True, exist_ok=True)
    p = Path(store) / f"{first:%Y-%m}.json.gz"
    part = p.with_name(p.name + ".part")
    part.write_bytes(gzip.compress(json.dumps(months, separators=(",", ":")).encode("utf-8")))
    part.replace(p)


def prune_store(store: Path, needed: set[date], keep_previous: bool = True) -> None:
    """Delete sky months no longer needed, so the cached store does not grow month after month.
    The month before the earliest needed one stays (it seeds the 1st of a month in western zones)."""
    keep = {f"{m:%Y-%m}" for m in needed}
    if keep_previous and needed:
        first = min(needed)
        keep.add(f"{(first - timedelta(days=1)):%Y-%m}")
    for p in Path(store).glob("*.json.gz"):
        if p.name[:7] not in keep:
            p.unlink()


def write_station_data(catalogue: list[dict], constants: dict, now: datetime, out: Path, sky_cache: Path,
                       workers: int = 1, sky_store: Path | None = None) -> dict:
    stations = constants["stations"]
    by_id = {r["id"]: r for r in catalogue}
    items = []
    for r in catalogue:
        today = now.astimezone(ZoneInfo(r["timezone"])).date()
        key = (round(float(r["latitude"]), SKY_ROUND), round(float(r["longitude"]), SKY_ROUND), r["timezone"],
               today.replace(day=1))
        entry = stations.get(r["id"])
        donor = None
        if entry and entry["kind"] == "donor":
            d = by_id.get(entry["donor"], {})
            donor = {"name": d.get("name"), "path": d.get("path")}
        items.append((r, today, donor, key))
    sky = load_sky(Path(sky_cache))
    first = (now - timedelta(days=2)).date().replace(day=1)
    coef = {first + timedelta(days=k): tidal_coefficient(first + timedelta(days=k), sky) for k in range(64)}

    # Pass 1: sky months, from the store or computed.
    needed = sorted({it[3] for it in items}, key=lambda k: (k[3], k[0], k[1], k[2]))
    stored = {m: _load_months(sky_store, m) for m in {k[3] for k in needed}}
    months: dict[tuple, list] = {}
    missing = []
    for k in needed:
        got = stored[k[3]].get(_key_text(k))
        if got is not None:
            months[k] = got
        else:
            missing.append(k)
    if workers > 1 and missing:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                                 initargs=(str(sky_cache), {}, {})) as pool:
            computed = list(pool.map(_sky_job, missing, chunksize=16))
    else:
        _init(str(sky_cache), {}, {})
        computed = [_sky_job(k) for k in missing]
    for k, month in computed:
        months[k] = month
        stored[k[3]][_key_text(k)] = month
    if sky_store is not None and computed:
        for m, data in stored.items():
            _save_months(sky_store, m, data)
    if sky_store is not None and Path(sky_store).exists():
        prune_store(sky_store, set(stored))

    # Pass 2: one file per station.
    del stored
    jobs = [(r, today, donor, months[key]) for r, today, donor, key in items]
    chunks = [(jobs[i:i + 200], str(out)) for i in range(0, len(jobs), 200)]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                                 initargs=(str(sky_cache), stations, coef)) as pool:
            written = sum(pool.map(_write_job, chunks))
    else:
        _init(str(sky_cache), stations, coef)
        written = sum(_write_job(c) for c in chunks)
    with_tides = sum(1 for r in catalogue if stations.get(r["id"], {}).get("kind", "none") != "none")
    return {"written": written, "with_tides": with_tides, "sky_computed": len(computed)}
