"""One tide-constants entry per catalogue station, following the spec §6 rules.

- NOAA harmonic station with published constants: ``harmonic`` (its constants, and its MSL
  above MLLW for subordinate stations that use it).
- NOAA subordinate station whose reference is a harmonic station within 1,000 km:
  ``subordinate`` (reference id and NOAA's offsets).
- Place whose nearby NOAA station (catalogue ``reference_station``) has a usable tide: ``donor``.
- Everything else: ``model`` (the global model at the nearest ocean node within 20 km), or
  ``none`` when there is no ocean that close.
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .sources.openmeteo import http_fetch
from .tide_predict import CONSTITUENTS

API = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations"
MAX_REF_KM = 1000.0
PAUSE_S = 0.5


class NoaaFetchError(RuntimeError):
    """Some NOAA requests failed: the stations they cover would silently fall back to the model."""


def _get(url: str, dest: Path, fetch: Callable[[str, Path], None], failed: list[str], pause: float) -> dict | None:
    if not dest.exists():
        time.sleep(pause)
        try:
            fetch(url, dest)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                failed.append(f"{url}: {exc}")
                return None  # not cached, so the next run tries again
            dest.write_text("{}", encoding="utf-8")  # NOAA has nothing for this station
        except Exception as exc:
            failed.append(f"{url}: {exc}")
            return None
    try:
        return json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def noaa_stations(path: Path) -> list[dict]:
    """[{id, type}] from NOAA's tide-prediction station list (the catalogue input)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [{"id": str(s["id"]), "type": s.get("type") or "R"} for s in data["stations"]]


def write_model_file(path: Path, label: str, samples: dict[str, list | None]) -> Path:
    """Model constants sampled at every station: {"model", "built", "stations": {id: cons | null}}."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"model": label, "built": _now(), "stations": samples}
    path.write_text(json.dumps(body, separators=(",", ":")), encoding="utf-8")
    return path


def read_model(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_noaa(stations: list[dict], cache: Path, fetch: Callable[[str, Path], None] | None = None,
               pause: float = PAUSE_S) -> dict[str, dict]:
    """Harmonic constants and datums for type R stations, offsets for type S; one file per request, cached.

    One request at a time with a pause between them (NOAA answers 403 to bursts). A 404 is
    cached as "nothing published"; any other failure raises NoaaFetchError once every station
    has been tried, so a partial run never ships with NOAA stations silently on the model.
    """
    fetch = fetch or http_fetch
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    requests = 0

    def _get_counted(url: str, dest: Path) -> dict | None:
        nonlocal requests
        requests += not dest.exists()
        return _get(url, dest, fetch, failed, pause)

    def one(st: dict) -> tuple[str, dict]:
        sid = str(st["id"])
        if st["type"] == "S":
            o = _get_counted(f"{API}/{sid}/tidepredoffsets.json", cache / f"{sid}-offsets.json") or {}
            if not o.get("refStationId"):
                return sid, {"type": "S", "offsets": None}
            return sid, {"type": "S", "offsets": {
                "ref": str(o["refStationId"]), "th": o.get("timeOffsetHighTide") or 0, "tl": o.get("timeOffsetLowTide") or 0,
                "hh": o.get("heightOffsetHighTide"), "hl": o.get("heightOffsetLowTide"),
                "kind": o.get("heightAdjustedType") or "R"}}
        h = _get_counted(f"{API}/{sid}/harcon.json?units=metric", cache / f"{sid}-harcon.json") or {}
        cons = [[c["name"], c["amplitude"], c["phase_GMT"]] for c in (h.get("HarmonicConstituents") or [])
                if c.get("amplitude") and c["name"] in CONSTITUENTS]  # NOAA predicts from its standard set
        d = None
        if cons:
            dat = _get_counted(f"{API}/{sid}/datums.json?units=metric", cache / f"{sid}-datums.json") or {}
            v = {x["name"]: x.get("value") for x in (dat.get("datums") or [])}
            if v.get("MSL") is not None and v.get("MLLW") is not None:
                d = round(v["MSL"] - v["MLLW"], 4)
        return sid, {"type": "R", "cons": cons, "msl_above_mllw": d}

    out = dict(one(st) for st in stations)
    if failed:
        raise NoaaFetchError(f"{len(failed)} of {requests} NOAA requests failed (rerun to continue from the cache); "
                             f"first: {failed[0]}")
    return out


def _km(a: dict, b: dict) -> float:
    p1, p2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    dl = math.radians(b["longitude"] - a["longitude"])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


def assign(records: list[dict], noaa: dict[str, dict], model: dict[str, list | None]) -> dict[str, dict]:
    by_id = {r["id"]: r for r in records}
    by_path = {r["path"]: r["id"] for r in records}
    out: dict[str, dict] = {}

    def from_model(sid: str) -> dict:
        cons = model.get(sid)
        return {"kind": "model", "cons": cons} if cons else {"kind": "none"}

    def usable_ref(ref: str) -> dict | None:
        info = noaa.get(ref)
        if info and info["type"] == "R" and info["cons"] and info.get("msl_above_mllw") is not None:
            return info
        return None

    for r in records:
        if r["type"] != "gauge":
            continue
        sid, nid = r["id"], r["id"][1:]
        info = noaa.get(nid)
        if info and info["type"] == "R" and info["cons"]:
            out[sid] = {"kind": "harmonic", "cons": info["cons"], "d": info.get("msl_above_mllw")}
        elif info and info["type"] == "S" and info.get("offsets") and info["offsets"].get("hh") is not None:
            o = info["offsets"]
            ref_rec = by_id.get(f"n{o['ref']}")
            if usable_ref(o["ref"]) and ref_rec and _km(r, ref_rec) <= MAX_REF_KM:
                out[sid] = {"kind": "subordinate", "ref": f"n{o['ref']}",
                            "offsets": [o["th"], o["tl"], o["hh"], o["hl"], o["kind"]]}
            else:
                out[sid] = from_model(sid)
        else:
            out[sid] = from_model(sid)

    for r in records:
        if r["type"] == "gauge":
            continue
        sid = r["id"]
        donor = by_path.get((r.get("reference_station") or {}).get("path", ""))
        if donor and out.get(donor, {}).get("kind") in ("harmonic", "subordinate"):
            out[sid] = {"kind": "donor", "donor": donor}
        else:
            out[sid] = from_model(sid)
    return out


def build_constants(records: list[dict], noaa: dict[str, dict], models: list[dict]) -> dict:
    """``tide-constants.json``: for each station the first model (in order) with constants there wins."""
    merged: dict[str, list] = {}
    source: dict[str, str] = {}
    for m in models:
        for sid, cons in m["stations"].items():
            if cons and sid not in merged:
                merged[sid], source[sid] = cons, m["model"]
    stations = assign(records, noaa, merged)
    for sid, e in stations.items():
        if e["kind"] == "model":
            e["source"] = source[sid]
    return {"v": 1, "built": _now(), "models": [m["model"] for m in models], "stations": stations}
