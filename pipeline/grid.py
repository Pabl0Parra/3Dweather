"""The globe's output grid: 768 x 384 equirectangular cells, row 0 at the north."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GlobeGrid:
    w: int
    h: int
    north: float
    west: float
    dlon: float
    dlat: float

    def lons(self) -> np.ndarray:
        return self.west + np.arange(self.w) * self.dlon

    def lats(self) -> np.ndarray:
        """Cell-centre latitudes, north to south."""
        return self.north - np.arange(self.h) * self.dlat

    def cell_of(self, lat: float, lon: float) -> tuple[int, int]:
        """(y, x) of the nearest cell; x wraps around the antimeridian."""
        y = int(np.clip(np.rint((self.north - lat) / self.dlat), 0, self.h - 1))
        x = int(np.rint((lon - self.west) / self.dlon)) % self.w
        return y, x

    def manifest_fields(self) -> dict:
        return {"w": self.w, "h": self.h, "north": self.north, "west": self.west,
                "dlon": self.dlon, "dlat": self.dlat}


GLOBE = GlobeGrid(w=768, h=384, north=89.7364, west=-179.82422, dlon=0.46875, dlat=0.468597)
