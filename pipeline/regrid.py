"""Bilinear regridding from a regular source grid, ignoring missing cells."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .grid import GlobeGrid


@dataclass(frozen=True)
class SourceGrid:
    """Regular lat/lon grid; row 0 is at lat0 and rows run northward."""
    lat0: float
    lon0: float
    dlat: float
    dlon: float
    wrap: bool = True


def regrid_bilinear(src: np.ndarray, sg: SourceGrid, grid: GlobeGrid) -> np.ndarray:
    """Sample src at every globe cell centre. A cell whose four neighbours are all
    missing is NaN; otherwise only the valid neighbours contribute."""
    rows, cols = src.shape
    fy = np.clip((grid.lats() - sg.lat0) / sg.dlat, 0.0, rows - 1.0)
    fx = (grid.lons() - sg.lon0) / sg.dlon
    if not sg.wrap:
        fx = np.clip(fx, 0.0, cols - 1.0)
    y0 = np.minimum(np.floor(fy).astype(np.intp), rows - 2)
    x0 = np.floor(fx).astype(np.intp)
    wy = (fy - y0)[:, None]
    wx = (fx - x0)[None, :]
    if sg.wrap:
        x1 = (x0 + 1) % cols
        x0 = x0 % cols
    else:
        x0 = np.minimum(x0, cols - 2)
        wx = (fx - x0)[None, :]
        x1 = x0 + 1
    y1 = y0 + 1

    valid = np.isfinite(src)
    values = np.where(valid, src, 0.0).astype(np.float64)
    num = np.zeros((grid.h, grid.w))
    den = np.zeros((grid.h, grid.w))
    for yi, wyy in ((y0, 1.0 - wy), (y1, wy)):
        for xi, wxx in ((x0, 1.0 - wx), (x1, wx)):
            weight = wyy * wxx * valid[np.ix_(yi, xi)]
            num += weight * values[np.ix_(yi, xi)]
            den += weight
    out = np.full((grid.h, grid.w), np.nan, dtype=np.float32)
    np.divide(num, den, out=out, where=den > 0, casting="unsafe")
    return out
