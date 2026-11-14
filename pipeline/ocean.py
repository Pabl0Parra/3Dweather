"""Ocean file (globe-c): current u, current v, sea temperature; 8 daily frames.

Frame k is the snapshot at globe hour 24k (k = 0..7). Snapshots matched the
reference's captured file at 0.03-0.04 mean byte difference; daily means were 2.5-3.3.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from PIL import Image

from .codecs import encode_current, encode_sea_temp
from .grid import GLOBE
from .regrid import SourceGrid, regrid
from .sprites import pack_chunk
from .waves import fill_land

CURRENT_FRAMES = 8
CURRENT_EVERY = 24


def ocean_time(globe_run: datetime, k: int) -> datetime:
    return globe_run + timedelta(hours=CURRENT_EVERY * k)


def ocean_frame(u: np.ndarray, v: np.ndarray, sst: np.ndarray, sg: SourceGrid) -> np.ndarray:
    """uint8 (384, 768, 3). Sea values are spread 4 cells into land like the waves."""
    cu, cv, cs = (fill_land(regrid(a, sg, GLOBE)) for a in (u, v, sst))
    return np.dstack([encode_current(cu), encode_current(cv), encode_sea_temp(cs)])


def pack_ocean(frames: list[np.ndarray]) -> Image.Image:
    assert len(frames) == CURRENT_FRAMES
    return pack_chunk(frames)
