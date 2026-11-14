"""Global maxima and minima per frame, for the "next seven days" summaries."""
from __future__ import annotations

import numpy as np

from .grid import GLOBE


def peak(field: np.ndarray, mode: str = "max", exclude: np.ndarray | None = None) -> list[float]:
    """[value (1 dp), lat (2 dp), lon (2 dp)] of the extreme globe cell, taken
    before byte rounding and land fill; cells in `exclude` are skipped; all-missing gives [0, 0, 0]."""
    if exclude is not None:
        field = np.where(exclude, np.nan, field)
    if not np.isfinite(field).any():
        return [0.0, 0.0, 0.0]
    i = np.nanargmax(field) if mode == "max" else np.nanargmin(field)
    y, x = np.unravel_index(i, field.shape)
    return [round(float(field[y, x]), 1), round(float(GLOBE.lats()[y]), 2), round(float(GLOBE.lons()[x]), 2)]


def hourly(frame_peaks: list[list[float]], every: int, hours: int) -> list[list[float]]:
    """One entry per hour 0..hours: the frame that hour falls in."""
    return [frame_peaks[min(h // every, len(frame_peaks) - 1)] for h in range(hours + 1)]
