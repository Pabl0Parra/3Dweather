"""Monthly tide tables: high and low waters for every station, 12 months either side of the run month.

``tides/{path}.json`` = ``{"v": 1, "id", "name", "tz", "source", "donor": {name, path} | null, "datum": "MSL",
"from", "to", "turns": [[minutes since from, height cm, 1 high | 0 low], ...]}``. Stations
without tides (``kind: none``, or missing from the constants) get no file and are listed in
``tides/index.json``.
"""
from __future__ import annotations

import json
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .tide_predict import Offsets, extrema, subordinate

UTC = timezone.utc
MONTHS_BEFORE = 12
MONTHS_AFTER = 13  # the run month and the 12 after it
REF_PAD = timedelta(hours=6)  # subordinate time offsets move turns across the window's edges


def _add_months(d: date, n: int) -> date:
    k = d.year * 12 + d.month - 1 + n
    return date(k // 12, k % 12 + 1, 1)


def table_window(run: date) -> tuple[datetime, datetime]:
    a, b = _add_months(run, -MONTHS_BEFORE), _add_months(run, MONTHS_AFTER)
    return datetime(a.year, a.month, 1, tzinfo=UTC), datetime(b.year, b.month, 1, tzinfo=UTC)


_REF_CACHE: "OrderedDict[tuple, list]" = OrderedDict()  # reference turns, per process
REF_CACHE_SIZE = 32


def _ref_extrema(ref_id: str, cons, start: datetime, end: datetime) -> list:
    """extrema() for a station other stations lean on (subordinates, donors), remembered briefly."""
    key = (ref_id, start, end)
    if key in _REF_CACHE:
        _REF_CACHE.move_to_end(key)
        return _REF_CACHE[key]
    turns = extrema(start, end, cons)
    _REF_CACHE[key] = turns
    if len(_REF_CACHE) > REF_CACHE_SIZE:
        _REF_CACHE.popitem(last=False)
    return turns


def station_turns(entry: dict, constants: dict[str, dict], start: datetime, end: datetime) -> list:
    """Turns in [start, end) for one tide-constants entry (``constants`` is the ``stations`` map)."""
    kind = entry["kind"]
    if kind in ("harmonic", "model"):
        return extrema(start, end, entry["cons"])
    if kind == "donor":
        donor = constants[entry["donor"]]
        if donor["kind"] == "harmonic":
            return list(_ref_extrema(entry["donor"], donor["cons"], start, end))
        return station_turns(donor, constants, start, end)
    if kind == "subordinate":
        ref = constants[entry["ref"]]
        base = _ref_extrema(entry["ref"], ref["cons"], start - REF_PAD, end + REF_PAD)
        turns = subordinate(base, Offsets(*entry["offsets"]), ref["d"])
        return [x for x in turns if start <= x[0] < end]
    return []


def _source(sid: str, entry: dict, constants: dict[str, dict]) -> str:
    kind = entry["kind"]
    if kind == "harmonic":
        return f"NOAA CO-OPS harmonic constants, station {sid[1:]} (public domain)"
    if kind == "subordinate":
        return f"NOAA CO-OPS offsets on station {entry['ref'][1:]} (public domain)"
    if kind == "donor":
        return _source(entry["donor"], constants[entry["donor"]], constants)
    return entry["source"]


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


_STATIONS: dict[str, dict] = {}  # the constants' station map, set once per worker process


def _init(stations: dict[str, dict]) -> None:
    global _STATIONS
    _STATIONS = stations


def _table(job: tuple) -> tuple[str, dict]:
    rec, entry, donor, start, end = job
    constants = _STATIONS
    turns = station_turns(entry, constants, start, end)
    rows = [[round((t - start).total_seconds() / 60), round(h * 100), 1 if k == "high" else 0] for t, h, k in turns]
    return rec["path"], {"v": 1, "id": rec["id"], "name": rec.get("name"), "tz": rec.get("timezone") or "UTC",
                         "source": _source(rec["id"], entry, constants), "donor": donor,
                         "datum": "MSL", "from": _iso(start), "to": _iso(end), "turns": rows}


def write_tables(catalogue: list[dict], constants: dict, run: date, out: Path, workers: int = 1) -> dict:
    start, end = table_window(run)
    out = Path(out)
    stations = constants["stations"]
    by_id = {r["id"]: r for r in catalogue}
    without, jobs = [], []
    for r in catalogue:
        entry = stations.get(r["id"])
        if not entry or entry["kind"] == "none":
            without.append(r["id"])
            continue
        donor = None
        if entry["kind"] == "donor":
            d = by_id.get(entry["donor"], {})
            donor = {"name": d.get("name"), "path": d.get("path")}
        jobs.append((r, entry, donor, start, end))

    def save(path: str, body: dict) -> None:
        p = out / f"{path}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(body, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(stations,)) as pool:
            for path, body in pool.map(_table, jobs, chunksize=32):
                save(path, body)
    else:
        _init(stations)
        for job in jobs:
            save(*_table(job))
    out.mkdir(parents=True, exist_ok=True)
    index = {"v": 1, "from": _iso(start), "to": _iso(end), "models": constants.get("models", []), "without": without}
    (out / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    return {"written": len(jobs), "without": len(without)}
