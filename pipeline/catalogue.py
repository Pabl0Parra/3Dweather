"""Station catalogue: NOAA CO-OPS tide-prediction stations plus GeoNames coastal places.

Selection is our own rule (the reference publishes none): every NOAA station, plus
GeoNames populated places (``cities500``) within ``COAST_KM`` of the Natural Earth
coastline, dropping a place within ``DEDUP_KM`` of a larger kept one.

Inputs (one folder, filled by ``fetch_inputs``): ``noaa-tidepredictions.json`` (CO-OPS
mdapi, public domain), GeoNames ``cities500.zip``, ``admin1CodesASCII.txt``,
``admin2Codes.txt``, ``countryInfo.txt`` (CC BY 4.0) and the Natural Earth coastline.
"""
from __future__ import annotations

import io
import json
import math
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path

from typing import Callable

import numpy as np

from .sources.openmeteo import http_fetch
from .static_assets import COAST, NATURAL_EARTH

COAST_KM = 4.5
DEDUP_KM = 0.5
DONOR_KM = 5.0  # a place this close to a NOAA station takes its tide (spec section 6)
LOCAL_KM = 300.0  # beyond this the nearest place says nothing about a gauge's zone or region
R_KM = 6371.0


# --- small helpers -------------------------------------------------------------------------

def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    out, dash = [], False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            dash = False
        elif not dash and out:
            out.append("-")
            dash = True
    return "".join(out).strip("-")


def _xyz(lat, lon) -> np.ndarray:
    la, lo = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)


def _km_from_dot(dot) -> np.ndarray:
    return R_KM * np.arccos(np.clip(dot, -1.0, 1.0))


def _etc_zone(corr) -> str:
    """NOAA's fixed UTC offset as an IANA zone (POSIX sign: Etc/GMT+10 is UTC-10)."""
    try:
        h = float(corr)
    except (TypeError, ValueError):
        return "UTC"
    if h != int(h) or abs(h) > 14:
        return "UTC"
    h = int(h)
    return "Etc/GMT" if h == 0 else f"Etc/GMT{-h:+d}"


# --- coastline distance --------------------------------------------------------------------

def coast_points(geojson: dict, step_deg: float = 0.005) -> np.ndarray:
    """Coastline vertices densified to ``step_deg``, as (lon, lat) rows."""
    parts = []
    for f in geojson["features"]:
        g = f["geometry"]
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for ln in lines:
            a = np.asarray(ln, float)[:, :2]
            if len(a) == 1:
                parts.append(a)
                continue
            for p, q in zip(a[:-1], a[1:]):
                n = max(1, int(math.ceil(float(np.hypot(*(q - p))) / step_deg)))
                t = np.arange(n, dtype=float)[:, None] / n
                parts.append(p + (q - p) * t)
            parts.append(a[-1:])
    return np.concatenate(parts) if parts else np.zeros((0, 2))


class CoastIndex:
    """Nearest-coast distance, exact within one 0.25° cell; 99 km when nothing is that close."""

    CELL = 0.25
    NJ = 1440

    def __init__(self, pts: np.ndarray):
        self.xyz = _xyz(pts[:, 1], pts[:, 0])
        key = self._key(pts[:, 1], pts[:, 0])
        self.order = np.argsort(key, kind="stable")
        self.uniq, self.start = np.unique(key[self.order], return_index=True)
        self.end = np.append(self.start[1:], len(key))

    def _cell(self, lat, lon):
        i = np.floor((np.asarray(lat) + 90.0) / self.CELL).astype(np.int64)
        j = np.floor((np.asarray(lon) + 180.0) / self.CELL).astype(np.int64) % self.NJ
        return i, j

    def _key(self, lat, lon):
        i, j = self._cell(lat, lon)
        return i * self.NJ + j

    def _points(self, i: int, j: int) -> np.ndarray | None:
        k = i * self.NJ + (j % self.NJ)
        n = np.searchsorted(self.uniq, k)
        if n < len(self.uniq) and self.uniq[n] == k:
            return self.order[self.start[n]:self.end[n]]
        return None

    def distance_km(self, lat, lon) -> np.ndarray:
        lat, lon = np.asarray(lat, float), np.asarray(lon, float)
        out = np.full(lat.shape, 99.0)
        if not len(self.uniq) or not lat.size:
            return out
        P = _xyz(lat, lon)
        key = self._key(lat, lon)
        order = np.argsort(key, kind="stable")
        keys, starts = np.unique(key[order], return_index=True)
        ends = np.append(starts[1:], len(order))
        for k, s, e in zip(keys, starts, ends):
            i, j = divmod(int(k), self.NJ)
            near = [p for a in (-1, 0, 1) for b in (-1, 0, 1) if (p := self._points(i + a, j + b)) is not None]
            if not near:
                continue
            members = order[s:e]
            dot = P[members] @ self.xyz[np.concatenate(near)].T
            out[members] = np.minimum(99.0, _km_from_dot(dot.max(axis=1)))
        return out


def _nearest(src_lat, src_lon, dst_lat, dst_lon, chunk: int = 64) -> tuple[np.ndarray, np.ndarray]:
    """For each source point, the index of and distance to the nearest destination point."""
    D = _xyz(dst_lat, dst_lon).astype(np.float32)
    S = _xyz(src_lat, src_lon).astype(np.float32)
    idx = np.zeros(len(S), np.int64)
    best = np.full(len(S), -2.0)
    for a in range(0, len(S), chunk):
        dot = S[a:a + chunk] @ D.T
        k = dot.argmax(axis=1)
        idx[a:a + chunk] = k
        best[a:a + chunk] = dot[np.arange(len(k)), k]
    # Recompute the winners in float64 for an accurate distance.
    km = _km_from_dot(np.einsum("ij,ij->i", _xyz(src_lat, src_lon), _xyz(np.asarray(dst_lat)[idx], np.asarray(dst_lon)[idx])))
    return idx, km


# --- inputs --------------------------------------------------------------------------------

NOAA_URL = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=tidepredictions"
GEONAMES = "https://download.geonames.org/export/dump"
INPUTS = {
    "noaa-tidepredictions.json": NOAA_URL,
    "cities500.zip": f"{GEONAMES}/cities500.zip",
    "admin1CodesASCII.txt": f"{GEONAMES}/admin1CodesASCII.txt",
    "admin2Codes.txt": f"{GEONAMES}/admin2Codes.txt",
    "countryInfo.txt": f"{GEONAMES}/countryInfo.txt",
    COAST: f"{NATURAL_EARTH}/{COAST}",
}


def fetch_inputs(inputs: Path, fetch: Callable[[str, Path], None] = http_fetch) -> Path:
    """Download whichever inputs are missing; returns the coastline path."""
    inputs = Path(inputs)
    inputs.mkdir(parents=True, exist_ok=True)
    for name, url in INPUTS.items():
        if name == "cities500.zip" and (inputs / "cities500.txt").exists():
            continue
        if not (inputs / name).exists():
            fetch(url, inputs / name)
    return inputs / COAST


def _read_cities(inputs: Path) -> list[list[str]]:
    txt = inputs / "cities500.txt"
    if txt.exists():
        text = txt.read_text(encoding="utf-8")
    else:
        with zipfile.ZipFile(inputs / "cities500.zip") as z:
            text = io.TextIOWrapper(z.open("cities500.txt"), encoding="utf-8").read()
    return [ln.split("\t") for ln in text.splitlines() if ln.strip()]


def _read_codes(path: Path) -> dict[str, tuple[str, str]]:
    """``code -> (name, ascii name)`` from admin1CodesASCII / admin2Codes."""
    out = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) >= 3:
            out[p[0]] = (p[1], p[2])
    return out


def read_countries(inputs: Path) -> dict[str, tuple[str, str]]:
    """``ISO code -> (country name, continent code)`` from countryInfo.txt."""
    out = {}
    for ln in (inputs / "countryInfo.txt").read_text(encoding="utf-8").splitlines():
        if not ln or ln.startswith("#"):
            continue
        p = ln.split("\t")
        if len(p) >= 9:
            out[p[0]] = (p[4], p[8])
    return out


# --- the catalogue -------------------------------------------------------------------------

def build_catalogue(inputs: Path, coast: Path) -> list[dict]:
    inputs = Path(inputs)
    cities = _read_cities(inputs)
    admin1 = _read_codes(inputs / "admin1CodesASCII.txt")
    admin2 = _read_codes(inputs / "admin2Codes.txt")
    countries = read_countries(inputs)
    noaa = json.loads((inputs / "noaa-tidepredictions.json").read_text(encoding="utf-8"))["stations"]

    c_lat = np.array([float(r[4]) for r in cities])
    c_lon = np.array([float(r[5]) for r in cities])
    c_pop = np.array([int(r[14] or 0) for r in cities])

    def region_of(cc: str, a1: str) -> tuple[str, str]:
        name, ascii_name = admin1.get(f"{cc}.{a1}", (None, None)) if a1 else (None, None)
        if not name:
            name = countries.get(cc, (cc, ""))[0]
            ascii_name = name
        return name, slugify(ascii_name) or slugify(name) or slugify(countries.get(cc, (cc,))[0]) or "region"

    def county_of(cc: str, a1: str, a2: str) -> str | None:
        return admin2.get(f"{cc}.{a1}.{a2}", (None,))[0] if a2 else None

    # Per US state, the nearest place's zone at any distance (remote Aleutian and Hawaiian gauges).
    state_zone = {}
    for st in {(sn.get("state") or "").strip() for sn in noaa}:
        rows = [k for k, r in enumerate(cities) if r[8] == "US" and r[10] == st and r[17]] if st else []
        if rows:
            def zone(lat, lon, rows=rows):
                i, _ = _nearest([lat], [lon], c_lat[rows], c_lon[rows])
                return cities[rows[int(i[0])]][17]
            state_zone[st] = zone

    # Gauges: every NOAA station, located through the nearest GeoNames place.
    gauges = []
    g_lat = np.array([float(s["lat"]) for s in noaa]) if noaa else np.zeros(0)
    g_lon = np.array([float(s["lng"]) for s in noaa]) if noaa else np.zeros(0)
    near_i, near_km = _nearest(g_lat, g_lon, c_lat, c_lon) if noaa else (np.zeros(0, int), np.zeros(0))
    for s, ni, nkm in zip(noaa, near_i, near_km):
        c = cities[ni]
        local = nkm <= LOCAL_KM
        state = (s.get("state") or "").strip()
        if state and f"US.{state}" in admin1:
            cc, (region, rslug) = "US", region_of("US", state)
            county = county_of("US", state, c[11]) if (c[8] == "US" and c[10] == state and nkm <= 50) else None
            if not local and state in state_zone:  # a remote gauge: the zone of its state's nearest place
                local_tz = state_zone[state](float(s["lat"]), float(s["lng"]))
            else:
                local_tz = None
        else:
            cc = c[8]
            region, rslug = region_of(cc, c[10]) if local else region_of(cc, "")
            county = county_of(cc, c[10], c[11]) if local else None
            local_tz = None
        name = " ".join(str(s["name"]).split())
        gauges.append({
            "id": f"n{s['id']}", "name": name, "_slug": slugify(name) or f"station-{s['id']}",
            "country_code": cc, "region_name": region, "region_slug": rslug, "county": county,
            "latitude": round(float(s["lat"]), 6), "longitude": round(float(s["lng"]), 6),
            "timezone": (c[17] or _etc_zone(s.get("timezonecorr"))) if local else (local_tz or _etc_zone(s.get("timezonecorr"))),
            "type": "gauge", "_pop": 0,
        })
    gauges.sort(key=lambda r: r["id"])

    # Places: coastal, then deduplicated, biggest first.
    dist = CoastIndex(coast_points(json.loads(Path(coast).read_text(encoding="utf-8")))).distance_km(c_lat, c_lon)
    cand = np.nonzero(dist <= COAST_KM)[0]
    cand = sorted(cand, key=lambda k: (-c_pop[k], int(cities[k][0])))
    kept, grid = [], defaultdict(list)
    cell = 0.01  # ~1.1 km, larger than DEDUP_KM
    for k in cand:
        gi, gj = int(math.floor(c_lat[k] / cell)), int(math.floor(c_lon[k] / cell))
        others = [o for a in (-1, 0, 1) for b in (-1, 0, 1) for o in grid.get((gi + a, gj + b), ())]
        if others:
            d = _km_from_dot(_xyz(c_lat[others], c_lon[others]) @ _xyz(c_lat[k], c_lon[k]))
            if d.min() <= DEDUP_KM:
                continue
        grid[(gi, gj)].append(k)
        kept.append(k)

    places = []
    for k in kept:
        r = cities[k]
        cc = r[8]
        region, rslug = region_of(cc, r[10])
        places.append({
            "id": f"g{r[0]}", "name": r[1], "_slug": slugify(r[1]) or slugify(r[2]) or f"place-{r[0]}",
            "country_code": cc, "region_name": region, "region_slug": rslug, "county": county_of(cc, r[10], r[11]),
            "latitude": round(float(r[4]), 6), "longitude": round(float(r[5]), 6),
            "timezone": r[17] or "UTC", "type": "place", "_pop": int(c_pop[k]),
        })

    # Unique paths, gauges first.
    taken: set[str] = set()
    out = []
    for rec in gauges + places:
        base = rec.pop("_slug")
        slug, n = base, 1
        while f"{rec['country_code'].lower()}/{rec['region_slug']}/{slug}" in taken:
            n += 1
            slug = f"{base}-{n}"
        path = f"{rec['country_code'].lower()}/{rec['region_slug']}/{slug}"
        taken.add(path)
        out.append({
            "id": rec["id"], "slug": slug, "name": rec["name"], "country_code": rec["country_code"],
            "region_name": rec["region_name"], "region_slug": rec["region_slug"], "county": rec["county"],
            "island": None, "latitude": rec["latitude"], "longitude": rec["longitude"], "timezone": rec["timezone"],
            "type": rec["type"], "has_tides": True, "has_current_station": False, "reference_station": None,
            "timing_offset_minutes": None, "path": path, "_pop": rec["_pop"],
        })

    # A place within DONOR_KM of a NOAA station takes that station's tide.
    gs = [r for r in out if r["type"] == "gauge"]
    ps = [r for r in out if r["type"] == "place"]
    if gs and ps:
        gi, gkm = _nearest([p["latitude"] for p in ps], [p["longitude"] for p in ps],
                           [g["latitude"] for g in gs], [g["longitude"] for g in gs])
        for p, i, d in zip(ps, gi, gkm):
            if d <= DONOR_KM:
                g = gs[i]
                p["reference_station"] = {"slug": g["slug"], "name": g["name"], "path": g["path"]}
    return out


def _rank(rec: dict) -> int:
    if rec["type"] == "gauge":
        return 9
    return max(0, min(8, int(math.log10(rec["_pop"] + 1))))


def write_catalogue(records: list[dict], inputs: Path, out: Path) -> None:
    """Write ``stations.json``, ``search.json`` and ``countries.json`` into ``out``."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    public = [{k: v for k, v in r.items() if not k.startswith("_")} for r in records]
    (out / "stations.json").write_text(json.dumps(public, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    rows = [[r["id"], r["name"], r["country_code"], r["region_name"], round(r["latitude"], 4), round(r["longitude"], 4),
             0 if r["type"] == "gauge" else 1, r["path"], _rank(r)] for r in records]
    search = {"v": 1, "fields": ["id", "name", "cc", "region", "lat", "lon", "type", "path", "rank"], "rows": rows}
    (out / "search.json").write_text(json.dumps(search, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    names = read_countries(inputs)
    by_cc: dict[str, dict] = {}
    for r in records:
        c = by_cc.setdefault(r["country_code"], {"count": 0, "regions": {}})
        c["count"] += 1
        reg = c["regions"].setdefault(r["region_slug"], {"slug": r["region_slug"], "name": r["region_name"], "count": 0})
        reg["count"] += 1
    countries = []
    for cc, c in sorted(by_cc.items(), key=lambda kv: (-kv[1]["count"], kv[0])):
        name, continent = names.get(cc, (cc, ""))
        regions = sorted(c["regions"].values(), key=lambda g: (-g["count"], g["slug"]))
        countries.append({"cc": cc, "name": name, "continent": continent, "count": c["count"], "regions": regions})
    (out / "countries.json").write_text(json.dumps(countries, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
