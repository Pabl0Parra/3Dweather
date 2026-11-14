"""Bilinear regridding from a regular source grid, ignoring missing cells."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

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


@dataclass(frozen=True)
class ReducedGaussian:
    """ECMWF octahedral reduced Gaussian grid O<n>: 2n rows, row i from the
    north holds 4(i+1)+16 points (mirrored south), starting at longitude 0."""
    n: int

    def lats(self) -> np.ndarray:
        return _gaussian_lats(self.n)

    def counts(self) -> np.ndarray:
        north = 4 * (np.arange(self.n) + 1) + 16
        return np.concatenate([north, north[::-1]])

    def offsets(self) -> np.ndarray:
        return np.concatenate([[0], np.cumsum(self.counts())[:-1]])


@lru_cache(maxsize=4)
def _gaussian_lats(n: int) -> np.ndarray:
    """2n Gaussian latitudes in degrees, north to south."""
    x, _ = np.polynomial.legendre.leggauss(2 * n)
    return np.degrees(np.arcsin(x))[::-1].copy()


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


def regrid(src: np.ndarray, sg: "SourceGrid | ReducedGaussian", grid: GlobeGrid) -> np.ndarray:
    if isinstance(sg, ReducedGaussian):
        return regrid_reduced_gaussian(src, sg, grid)
    return regrid_bilinear(src, sg, grid)


def regrid_reduced_gaussian(src: np.ndarray, rg: ReducedGaussian, grid: GlobeGrid) -> np.ndarray:
    """Linear in longitude along the two Gaussian rows around each globe latitude,
    then linear in latitude. Missing points are skipped by weight."""
    flat = np.asarray(src, dtype=np.float64).ravel()
    lats, counts, offsets = rg.lats(), rg.counts(), rg.offsets()
    lons = np.mod(grid.lons(), 360.0)
    out = np.full((grid.h, grid.w), np.nan, dtype=np.float32)
    for y, lat in enumerate(grid.lats()):
        # lats run north to south: row i is the last one at or north of lat
        i = int(np.searchsorted(-lats, -lat, side="right")) - 1
        if i < 0:
            rows = ((0, 1.0),)
        elif i >= len(lats) - 1:
            rows = ((len(lats) - 1, 1.0),)
        else:
            t = (lats[i] - lat) / (lats[i] - lats[i + 1])
            rows = ((i, 1.0 - t), (i + 1, t))
        num = np.zeros(grid.w)
        den = np.zeros(grid.w)
        for r, wr in rows:
            c = int(counts[r])
            row = flat[offsets[r]:offsets[r] + c]
            f = lons / (360.0 / c)
            j0 = np.floor(f).astype(np.intp)
            wx = f - j0
            for j, w in ((j0 % c, 1.0 - wx), ((j0 + 1) % c, wx)):
                v = row[j]
                ok = np.isfinite(v)
                ww = wr * w * ok
                num += ww * np.where(ok, v, 0.0)
                den += ww
        np.divide(num, den, out=out[y], where=den > 0, casting="unsafe")
    return out
