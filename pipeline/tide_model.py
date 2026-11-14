"""Global ocean tide models sampled at stations: EOT20 now, FES2022 once licensed.

Both come as one netCDF file per constituent (amplitude in cm, Greenwich phase lag in
degrees, lat south to north, lon 0..360 with 360 repeating 0). ``sample_model`` takes the
nearest ocean node within ``MAX_KM`` of each station and returns its constants under
NOAA's constituent names. The FES2022 run happens on the owner's machine
(``tools/fes2022_constants.py``), so FES2022 itself never reaches a runner.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .tide_atlas import _open, drop_artifacts

MAX_KM = 20.0
R_KM = 6371.0

EOT20_NAMES = {n: n for n in ["2N2", "J1", "K1", "K2", "M2", "M4", "MF", "MM", "N2", "O1", "P1", "Q1",
                              "S1", "S2", "SA", "SSA", "T2"]}
FES2022_NAMES = {
    "2n2": "2N2", "eps2": "EPS2", "j1": "J1", "k1": "K1", "k2": "K2", "l2": "L2", "lambda2": "LAM2", "m2": "M2",
    "m3": "M3", "m4": "M4", "m6": "M6", "m8": "M8", "mf": "MF", "mks2": "MKS2", "mm": "MM", "mn4": "MN4",
    "ms4": "MS4", "msf": "MSF", "msqm": "MSQM", "mtm": "MTM", "mu2": "MU2", "n2": "N2", "n4": "N4", "nu2": "NU2",
    "o1": "O1", "p1": "P1", "q1": "Q1", "r2": "R2", "s1": "S1", "s2": "S2", "s4": "S4", "sa": "SA", "ssa": "SSA",
    "t2": "T2",
}


def _regrid(lat, lon, amp_cm, phase):
    """To lat north-to-south, lon -180..180 (180 repeating -180), amplitude m with NaN on land."""
    amp = amp_cm.astype(np.float64)
    amp = np.where(~np.isfinite(amp) | (amp <= 0) | (amp > 1e4), np.nan, amp / 100.0)
    phase = phase.astype(np.float64)
    n = lon.size - 1
    half = int(np.argmin(np.abs(lon - 180.0)))
    order = np.r_[np.arange(half, n), np.arange(0, half), half]
    lon = np.where(lon[order] >= 180, lon[order] - 360, lon[order]).astype(np.float64)
    lon[-1] = 180.0
    return lat[::-1].astype(np.float64), lon, amp[::-1][:, order], phase[::-1][:, order]


@dataclass
class ModelReader:
    label: str
    names: dict[str, str]  # file constituent name -> NOAA name
    read: Callable[[str], tuple]  # file name -> (lat, lon, amp m, phase deg)

    @classmethod
    def eot20(cls, source: Path, names: list[str] | None = None) -> "ModelReader":
        def read(name):
            with _open(source, name) as f:
                return _regrid(f["lat"][:], f["lon"][:], f["amplitude"][:], f["phase"][:])
        chosen = {n: EOT20_NAMES[n] for n in (names or EOT20_NAMES)}
        return cls("EOT20 ocean tide (Hart-Davis et al. 2021, DGFI-TUM), CC BY 4.0", chosen, read)

    @classmethod
    def fes2022(cls, folder: Path, names: list[str] | None = None) -> "ModelReader":
        import h5py

        def read(name):
            with h5py.File(Path(folder) / f"{name}_fes2022.nc", "r") as f:
                return _regrid(f["lat"][:], f["lon"][:], f["amplitude"][:], f["phase"][:])
        chosen = {n: FES2022_NAMES[n] for n in (names or FES2022_NAMES)}
        return cls("FES2022 ocean tide (CNES, LEGOS, NOVELTIS, CLS; distributed by AVISO)", chosen, read)


def _nearest_ocean(lat: np.ndarray, lon: np.ndarray, ocean: np.ndarray, plat: float, plon: float):
    """(row, col) of the nearest ocean node within MAX_KM, or None."""
    dlat = abs(float(lat[1] - lat[0]))
    dlon = abs(float(lon[1] - lon[0]))
    i0 = int(np.argmin(np.abs(lat - plat)))
    j0 = int(np.argmin(np.abs(lon - plon)))
    ki = int(math.ceil(MAX_KM / (111.2 * dlat))) + 1
    kj = int(math.ceil(MAX_KM / (111.2 * dlon * max(0.05, math.cos(math.radians(plat)))))) + 1
    kj = min(kj, lon.size // 2)
    rows = np.arange(max(0, i0 - ki), min(lat.size, i0 + ki + 1))
    cols = np.arange(j0 - kj, j0 + kj + 1) % (lon.size - 1)  # last column repeats the first
    sub = ocean[np.ix_(rows, cols)]
    if not sub.any():
        return None
    la = np.radians(lat[rows])[:, None]
    lo = np.radians(lon[cols])[None, :]
    p1, l1 = math.radians(plat), math.radians(plon)
    a = np.sin((la - p1) / 2) ** 2 + np.cos(p1) * np.cos(la) * np.sin((lo - l1) / 2) ** 2
    d = 2 * R_KM * np.arcsin(np.sqrt(np.minimum(1.0, a)))
    d = np.where(sub, d, np.inf)
    k = np.unravel_index(int(np.argmin(d)), d.shape)
    if d[k] > MAX_KM:
        return None
    return int(rows[k[0]]), int(cols[k[1]])


def sample_model(records: list[dict], reader: ModelReader) -> dict[str, list | None]:
    """Per station id: [[NOAA name, amplitude m, phase deg], ...] at the nearest ocean node, or None."""
    files = list(reader.names)
    first = next((f for f in files if reader.names[f] == "M2"), files[0])
    lat, lon, amp, _ = reader.read(first)
    ocean = np.isfinite(drop_artifacts(amp))
    where = {r["id"]: _nearest_ocean(lat, lon, ocean, float(r["latitude"]), float(r["longitude"])) for r in records}
    picks = [(sid, ij) for sid, ij in where.items() if ij is not None]
    rows = np.array([ij[0] for _, ij in picks], dtype=np.int64)
    cols = np.array([ij[1] for _, ij in picks], dtype=np.int64)
    out: dict[str, list | None] = {sid: (None if ij is None else []) for sid, ij in where.items()}
    for f in files:
        _, _, a, g = reader.read(f)
        a = drop_artifacts(a)
        av, gv = a[rows, cols], g[rows, cols]
        for (sid, _), x, y in zip(picks, av, gv):
            if np.isfinite(x):
                out[sid].append([reader.names[f], round(float(x), 4), round(float(y) % 360.0, 1)])
    return {sid: (v if v else None) for sid, v in out.items()}
