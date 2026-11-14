"""Global tide atlas texture from EOT20 (CC BY 4.0), the stand-in for FES2022.

8 constituents averaged to a 0.5° grid and packed into one RGB PNG of 6 tiles
(720 x 2160). Channel 2k holds X = A cos G and 2k+1 holds Y = A sin G (metres,
byte = round(v / amax * 127) + 128); channel 16 is the sea mask; 17 is spare.
tide.json carries the grid, amax, speeds and the monthly nodal table.
"""
from __future__ import annotations

import io
import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from .tide_astro import CONSTITUENTS, SPEEDS_RAD_PER_HOUR, month_starts, nodal

ATLAS_W, ATLAS_H, TILES = 720, 360, 6
CELL = 0.5
WEST, NORTH = -180 + CELL / 2, 90 - CELL / 2
SOURCE = ("EOT20 ocean tide (Hart-Davis et al. 2021, DGFI-TUM), CC BY 4.0; "
          "8 constituents, 0.5 deg. Stand-in until FES2022 is licensed.")
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
MONTHS = 120


def _open(source: Path, name: str):
    """The constituent's netCDF4 (HDF5) file as a readable object: from a folder of
    *_ocean_eot20.nc files, or straight from the downloaded EOT20 zip (nested ocean_tides.zip)."""
    import h5py  # optional dependency: pip install -e ".[tides]"
    source = Path(source)
    fname = f"{name.upper()}_ocean_eot20.nc"
    if source.is_dir():
        return h5py.File(source / fname, "r")
    with zipfile.ZipFile(source) as outer:
        inner_bytes = outer.read("ocean_tides.zip") if "ocean_tides.zip" in outer.namelist() else None
    inner = zipfile.ZipFile(io.BytesIO(inner_bytes)) if inner_bytes else zipfile.ZipFile(source)
    with inner:
        data = inner.read(f"ocean_tides/{fname}")
    return h5py.File(io.BytesIO(data), "r")


def read_constituent(source: Path, name: str):
    """(lat north-to-south, lon -180..180 inclusive, amplitude m with NaN on land, phase deg)."""
    with _open(source, name) as f:
        lat, lon = f["lat"][:], f["lon"][:]
        amp, phase = f["amplitude"][:].astype(np.float64), f["phase"][:].astype(np.float64)
    amp = np.where(amp == 0, np.nan, amp / 100.0)  # cm -> m; 0 is the fill value on land
    # lon 0..360 with 360 repeating 0 -> -180..180 with 180 repeating -180
    n = lon.size - 1
    half = int(np.argmin(np.abs(lon - 180.0)))
    order = np.r_[np.arange(half, n), np.arange(0, half), half]
    lon = np.where(lon[order] >= 180, lon[order] - 360, lon[order])
    lon[-1] = 180.0
    amp, phase = amp[:, order], phase[:, order]
    return lat[::-1], lon, amp[::-1], phase[::-1]


def drop_artifacts(amp: np.ndarray) -> np.ndarray:
    """EOT20 has a few absurd estuary values (S2 31 m in the St. Lawrence): nodes above
    3x the constituent's 99.99th percentile are treated as no data."""
    limit = 3 * np.nanpercentile(amp, 99.99)
    return np.where(amp > limit, np.nan, amp)


def _trapezoid_mean(values: np.ndarray, sea: np.ndarray, factor: int, axis: int):
    """Weighted sums over each run of factor+1 nodes (edge nodes at half weight)."""
    w = np.ones(factor + 1)
    w[0] = w[-1] = 0.5
    count = (values.shape[axis] - 1) // factor
    total, weight = 0.0, 0.0
    for k in range(factor + 1):
        idx = [slice(None)] * values.ndim
        idx[axis] = slice(k, k + factor * count, factor)
        total = total + w[k] * values[tuple(idx)]
        weight = weight + w[k] * sea[tuple(idx)]
    return total, weight


def to_atlas_grid(lat, lon, amp, phase):
    """Complex mean of A·e^{iG} over the sea nodes of each 0.5° cell: (X, Y, sea mask)."""
    step = float(abs(lat[1] - lat[0]))
    factor = int(round(CELL / step))
    sea = np.isfinite(amp)
    g = np.radians(phase)
    z = np.where(sea, np.nan_to_num(amp) * np.exp(1j * g), 0)
    zs, ws = _trapezoid_mean(z, sea.astype(np.float64), factor, axis=1)
    z2, _ = _trapezoid_mean(zs, np.ones_like(ws), factor, axis=0)
    w2, _ = _trapezoid_mean(ws, np.ones_like(ws), factor, axis=0)
    has = w2 > 0
    mean = np.where(has, z2 / np.where(has, w2, 1), 0)
    assert mean.shape == (ATLAS_H, ATLAS_W), mean.shape
    return mean.real, mean.imag, has


def encode_atlas(fields: dict) -> tuple[np.ndarray, dict]:
    """fields: name -> (X, Y, sea). Returns the 2160x720x3 image and amax per constituent."""
    channels = np.full((TILES * 3, ATLAS_H, ATLAS_W), 128, np.uint8)
    amax, sea_all = {}, np.zeros((ATLAS_H, ATLAS_W), bool)
    for k, name in enumerate(CONSTITUENTS):
        X, Y, sea = fields[name]
        A = np.hypot(X, Y)
        # 99.99th percentile: the handful of cells above it (estuary artifacts) are scaled
        # down to amax with their phase kept, instead of costing everyone precision.
        a = float(np.percentile(A[sea], 99.99)) if sea.any() else 0.0
        amax[name] = round(max(a, 1e-4), 4)
        scale = np.minimum(1.0, amax[name] / np.where(A > 0, A, 1))
        X, Y = X * scale, Y * scale
        for comp, v in ((0, X), (1, Y)):
            b = np.rint(np.where(sea, v, 0) / amax[name] * 127) + 128
            channels[2 * k + comp] = np.clip(b, 1, 255).astype(np.uint8)
        sea_all |= sea
    channels[16] = np.where(sea_all, 255, 0)
    channels[17] = 0
    img = np.concatenate([np.stack(channels[3 * t:3 * t + 3], axis=-1) for t in range(TILES)], axis=0)
    return img, amax


def monthly_table(start: datetime = START, months: int = MONTHS) -> list[list[float]]:
    rows = []
    for t in month_starts(start, months):
        n = nodal(t)
        rows.append([round(v, 6) for name in CONSTITUENTS for v in n[name]])
    return rows


def build_tide_atlas(source: Path, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = {}
    for name in CONSTITUENTS:
        lat, lon, amp, phase = read_constituent(source, name)
        fields[name] = to_atlas_grid(lat, lon, drop_artifacts(amp), phase)
    img, amax = encode_atlas(fields)
    png = out_dir / "tide.png"
    Image.fromarray(img, "RGB").save(png.with_name("tide.png.part"), format="PNG", optimize=True)
    png.with_name("tide.png.part").replace(png)
    meta = {"source": SOURCE, "cons": CONSTITUENTS, "w": ATLAS_W, "h": ATLAS_H, "tiles": TILES,
            "west": WEST, "north": NORTH, "dlon": CELL, "dlat": CELL, "amax": amax,
            "start": START.strftime("%Y-%m-%dT%H:%M:%SZ"), "speed": [round(s, 10) for s in SPEEDS_RAD_PER_HOUR],
            "months": monthly_table()}
    js = out_dir / "tide.json"
    js.with_name("tide.json.part").write_text(json.dumps(meta, separators=(",", ":")))
    js.with_name("tide.json.part").replace(js)
