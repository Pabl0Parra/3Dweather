"""Turns native wave grids into one globe frame: R = height, G/B = travel vector."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from .codecs import encode_vector, encode_wave_height, wave_vector
from .grid import GLOBE
from .regrid import SourceGrid, regrid_bilinear
from .sprites import EVERY


def frame_time(run: datetime, j: int) -> datetime:
    return run + timedelta(hours=EVERY * j)


def fill_land(field: np.ndarray, passes: int = 4) -> np.ndarray:
    """Extend sea values a few cells into land so the coast clips cleanly.
    Each pass gives an empty cell the mean of its valid 8 neighbours; columns wrap."""
    out = field.astype(np.float32, copy=True)
    for _ in range(passes):
        valid = np.isfinite(out)
        if valid.all():
            break
        values = np.where(valid, out, 0.0)
        total = np.zeros(out.shape, dtype=np.float64)
        count = np.zeros(out.shape, dtype=np.int32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                v = np.roll(values, dx, axis=1)
                m = np.roll(valid, dx, axis=1)
                if dy:
                    v, m = np.roll(v, dy, axis=0), np.roll(m, dy, axis=0)
                    edge = 0 if dy == 1 else -1  # rows do not wrap over the poles
                    v[edge], m[edge] = 0.0, False
                total += v
                count += m
        fill = ~valid & (count > 0)
        out[fill] = (total[fill] / count[fill]).astype(np.float32)
    return out


def wave_frame(height: np.ndarray, period: np.ndarray, direction: np.ndarray,
               sg: SourceGrid) -> np.ndarray:
    """uint8 (384, 768, 3). Vector components are interpolated, not angles, so
    directions stay correct across 0/360 degrees."""
    vx, vy = wave_vector(direction, period)
    h, x, y = (fill_land(regrid_bilinear(a, sg, GLOBE)) for a in (height, vx, vy))
    g, b = encode_vector(x, y)
    return np.dstack([encode_wave_height(h), g, b])


def wave_peak(height_native: np.ndarray, sg: SourceGrid) -> list[float]:
    """[metres, lat, lon] of the highest globe cell after regridding (before byte
    rounding and land fill). This reproduces the reference peaks exactly."""
    on_globe = regrid_bilinear(height_native, sg, GLOBE)
    if not np.isfinite(on_globe).any():
        return [0.0, 0.0, 0.0]
    y, x = np.unravel_index(np.nanargmax(on_globe), on_globe.shape)
    return [round(float(on_globe[y, x]), 1),
            round(float(GLOBE.lats()[y]), 2), round(float(GLOBE.lons()[x]), 2)]
