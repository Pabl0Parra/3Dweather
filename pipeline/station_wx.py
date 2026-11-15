"""Weather and sea at every catalogue station, for each forecast run (spec §5 step 6).

The run's frames are sampled at each station's nearest cell (native grid where the
pipeline reads one, otherwise the globe grid; marine fields at the nearest sea cell
within SEA_CELLS) and written as one file per country and region:
``stations/{cc}/{region}.json`` = ``{"v": 1, "run", "start", "step_h", "n", "fields",
"scale", "stations": {id: {field: [int | null, ...]}}}``; a value is ``round(x * scale)``.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

from .grid import GlobeGrid
from .regrid import SourceGrid

# field -> scale (stored value = round(x * scale))
FIELDS = {
    "t": 10,     # air temperature, °C
    "ws": 10,    # wind speed, m/s
    "wd": 1,     # wind direction (from), degrees
    "g": 10,     # gust, m/s (IFS; null past its hours)
    "r": 10,     # rain, mm/h
    "c": 1,      # cloud, %
    "p": 10,     # sea-level pressure, hPa
    "wh": 100,   # wave height, m
    "wp": 10,    # wave period, s
    "wdir": 1,   # wave direction, degrees
    "sst": 10,   # sea surface temperature, °C (daily)
}
CARRY = {"sst"}  # daily fields: each time takes the last value at or before it
SEA_CELLS = 3


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%MZ")


class StationSampler:
    def __init__(self, records: list[dict], times: list[datetime]):
        self.records = records
        self.times = list(times)
        self.lat = np.array([float(r["latitude"]) for r in records])
        self.lon = np.array([float(r["longitude"]) for r in records])
        self._idx: dict = {}
        self._sea: dict = {}
        self._data: dict[str, dict[datetime, np.ndarray]] = defaultdict(dict)

    def _cells(self, grid, shape) -> tuple[np.ndarray, np.ndarray]:
        key = (grid, shape)
        if key not in self._idx:
            ny, nx = shape
            if isinstance(grid, GlobeGrid):
                rows = np.rint((grid.north - self.lat) / grid.dlat)
                cols = np.rint((self.lon - grid.west) / grid.dlon)
            elif isinstance(grid, SourceGrid):
                rows = np.rint((self.lat - grid.lat0) / grid.dlat)
                cols = np.rint((self.lon - grid.lon0) / grid.dlon)
            else:
                raise TypeError(f"sample on a SourceGrid or the globe grid, not {type(grid).__name__}")
            self._idx[key] = (np.clip(rows, 0, ny - 1).astype(np.int64), cols.astype(np.int64) % nx)
        return self._idx[key]

    def _sea_cells(self, grid, field: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Nearest finite cell within SEA_CELLS of each station's cell (-1 where none), from the
        first field seen on this grid (the land mask does not change between times)."""
        key = (grid, field.shape)
        if key not in self._sea:
            rows, cols = self._cells(grid, field.shape)
            ny, nx = field.shape
            ok = np.isfinite(field)
            r_out, c_out = rows.copy(), cols.copy()
            offsets = sorted(((dy, dx) for dy in range(-SEA_CELLS, SEA_CELLS + 1)
                              for dx in range(-SEA_CELLS, SEA_CELLS + 1)), key=lambda o: o[0] ** 2 + o[1] ** 2)
            for k in range(len(rows)):
                for dy, dx in offsets:
                    y, x = rows[k] + dy, (cols[k] + dx) % nx
                    if 0 <= y < ny and ok[y, x]:
                        r_out[k], c_out[k] = y, x
                        break
                else:
                    r_out[k] = -1
            self._sea[key] = (r_out, c_out)
        return self._sea[key]

    def _sample(self, field: np.ndarray, grid, sea: bool) -> np.ndarray:
        rows, cols = self._sea_cells(grid, field) if sea else self._cells(grid, field.shape)
        out = np.full(len(rows), np.nan, dtype=np.float64)
        good = rows >= 0
        out[good] = field[rows[good], cols[good]]
        return out

    def add(self, t: datetime, name: str, field: np.ndarray, grid, sea: bool = False) -> None:
        if name not in FIELDS:
            raise KeyError(name)
        self._data[name][t] = self._sample(np.asarray(field), grid, sea)

    def add_wind(self, t: datetime, u: np.ndarray, v: np.ndarray, grid) -> None:
        uu, vv = self._sample(np.asarray(u), grid, False), self._sample(np.asarray(v), grid, False)
        self._data["ws"][t] = np.hypot(uu, vv)
        self._data["wd"][t] = np.degrees(np.arctan2(-uu, -vv)) % 360.0

    def values(self, name: str, t: datetime) -> np.ndarray:
        return self._data[name][t]

    def _series(self, name: str) -> np.ndarray:
        """[station, time] for one field, NaN where missing."""
        out = np.full((len(self.records), len(self.times)), np.nan)
        got = self._data.get(name, {})
        if name in CARRY:
            known = sorted(got)
            for j, t in enumerate(self.times):
                before = [u for u in known if u <= t]
                if before:
                    out[:, j] = got[before[-1]]
        else:
            for j, t in enumerate(self.times):
                if t in got:
                    out[:, j] = got[t]
        return out

    def write(self, run_dir: Path, run_iso: str) -> int:
        """Write stations/{cc}/{region}.json; returns the number of files."""
        scaled = {}
        for name, scale in FIELDS.items():
            s = self._series(name) * scale
            scaled[name] = [[None if not np.isfinite(x) else int(round(x)) for x in row] for row in s]
        groups: dict[tuple[str, str], dict] = defaultdict(dict)
        for i, r in enumerate(self.records):
            key = (str(r.get("country_code") or "xx").lower(), r.get("region_slug") or "_")
            groups[key][r["id"]] = {name: scaled[name][i] for name in FIELDS}
        base = {"v": 1, "run": run_iso, "start": _iso(self.times[0]) if self.times else None,
                "step_h": round((self.times[1] - self.times[0]).total_seconds() / 3600) if len(self.times) > 1 else 0,
                "n": len(self.times), "fields": list(FIELDS), "scale": FIELDS}
        for (cc, region), stations in groups.items():
            p = Path(run_dir) / "stations" / cc / f"{region}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({**base, "stations": stations}, separators=(",", ":")), encoding="utf-8")
        return len(groups)
