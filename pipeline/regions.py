"""The 12 flat regional maps: catalogue, grid and sampling.

A regional grid takes every second node of the GFS 13 km grid (0.234375 deg in
longitude), hourly for 72 h. Bounds are our own except Europe's, which matches
the captured reference manifest exactly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .regrid import SourceGrid

EPS = 1e-6
STEP = 2  # source nodes per regional cell


@dataclass(frozen=True)
class Region:
    slug: str
    title: str
    description: str
    west: float
    east: float
    south: float
    north: float
    focus: tuple[float, float, float, float]  # west, south, east, north of the opening view
    tz: str
    place: str  # the city whose time the page shows
    cities: list[tuple[str, float, float]] = field(default_factory=list)


REGIONS: list[Region] = [
    Region("united-states", "United States", "Wind, rain and clouds over the United States and its coasts.",
           -127.0, -65.0, 23.5, 50.0, (-125.0, 24.5, -66.5, 49.5), "America/New_York", "New York",
           [("New York", 40.71, -74.01), ("Los Angeles", 34.05, -118.24), ("Chicago", 41.88, -87.63),
            ("Houston", 29.76, -95.37), ("Miami", 25.76, -80.19), ("Seattle", 47.61, -122.33),
            ("San Francisco", 37.77, -122.42), ("Boston", 42.36, -71.06), ("New Orleans", 29.95, -90.07),
            ("Denver", 39.74, -104.99)]),
    Region("united-kingdom", "United Kingdom", "Wind, rain and clouds over Britain, Ireland and the seas around them.",
           -11.5, 3.0, 49.3, 61.0, (-9.0, 49.8, 2.2, 59.5), "Europe/London", "London",
           [("London", 51.51, -0.13), ("Manchester", 53.48, -2.24), ("Birmingham", 52.49, -1.89),
            ("Glasgow", 55.86, -4.25), ("Edinburgh", 55.95, -3.19), ("Cardiff", 51.48, -3.18),
            ("Belfast", 54.60, -5.93), ("Plymouth", 50.38, -4.14), ("Newcastle", 54.98, -1.61),
            ("Aberdeen", 57.15, -2.09)]),
    Region("scotland", "Scotland", "Wind, rain and clouds over Scotland, the Hebrides, Orkney and Shetland.",
           -11.0, 1.0, 54.0, 61.3, (-8.0, 54.6, -0.6, 60.9), "Europe/London", "Edinburgh",
           [("Edinburgh", 55.95, -3.19), ("Glasgow", 55.86, -4.25), ("Aberdeen", 57.15, -2.09),
            ("Inverness", 57.48, -4.22), ("Dundee", 56.46, -2.97), ("Stornoway", 58.21, -6.39),
            ("Lerwick", 60.15, -1.15), ("Oban", 56.41, -5.47), ("Kirkwall", 58.98, -2.96)]),
    Region("ireland", "Ireland", "Wind, rain and clouds over the island of Ireland and its coasts.",
           -14.0, -3.0, 50.5, 56.5, (-10.7, 51.3, -5.3, 55.5), "Europe/Dublin", "Dublin",
           [("Dublin", 53.35, -6.26), ("Cork", 51.90, -8.47), ("Galway", 53.27, -9.05),
            ("Limerick", 52.66, -8.63), ("Belfast", 54.60, -5.93), ("Waterford", 52.26, -7.11),
            ("Sligo", 54.27, -8.47), ("Derry", 54.99, -7.31), ("Killarney", 52.06, -9.51)]),
    Region("europe", "Europe", "Wind, rain and clouds over Europe and the North Atlantic, from Iceland to the Mediterranean.",
           -39.9609375, 41.8359375, 33.09469096091206, 71.9882746742671, (-28.0, 34.0, 38.0, 64.0),
           "Europe/London", "London",
           [("London", 51.51, -0.13), ("Paris", 48.86, 2.35), ("Berlin", 52.52, 13.40), ("Madrid", 40.42, -3.70),
            ("Rome", 41.90, 12.50), ("Lisbon", 38.72, -9.14), ("Dublin", 53.35, -6.26), ("Amsterdam", 52.37, 4.90),
            ("Copenhagen", 55.68, 12.57), ("Oslo", 59.91, 10.75), ("Stockholm", 59.33, 18.07),
            ("Reykjavík", 64.15, -21.94), ("Warsaw", 52.23, 21.01), ("Athens", 37.98, 23.73),
            ("Marseille", 43.30, 5.37), ("Bergen", 60.39, 5.32)]),
    Region("india", "India", "Wind, rain and clouds over India, Sri Lanka, the Arabian Sea and the Bay of Bengal.",
           66.0, 93.0, 5.0, 25.0, (67.0, 6.0, 92.0, 24.5), "Asia/Kolkata", "Mumbai",
           [("Mumbai", 19.08, 72.88), ("Chennai", 13.08, 80.27), ("Kolkata", 22.57, 88.36), ("Panaji", 15.49, 73.83),
            ("Kochi", 9.93, 76.27), ("Visakhapatnam", 17.69, 83.22), ("Colombo", 6.93, 79.86),
            ("Puducherry", 11.94, 79.81), ("Mangaluru", 12.91, 74.86), ("Thiruvananthapuram", 8.52, 76.94)]),
    Region("west-pacific", "East Asia and the West Pacific", "Wind, rain and clouds from the South China Sea to Japan and Guam.",
           100.0, 150.0, 0.0, 46.0, (102.0, 2.0, 148.0, 45.0), "Asia/Tokyo", "Tokyo",
           [("Tokyo", 35.68, 139.69), ("Seoul", 37.57, 126.98), ("Shanghai", 31.23, 121.47),
            ("Hong Kong", 22.32, 114.17), ("Taipei", 25.03, 121.57), ("Manila", 14.60, 120.98),
            ("Osaka", 34.69, 135.50), ("Naha", 26.21, 127.68), ("Hagåtña", 13.48, 144.75),
            ("Ho Chi Minh City", 10.82, 106.63), ("Busan", 35.18, 129.08)]),
    Region("philippines", "Philippines", "Wind, rain and clouds over the Philippine islands and the seas around them.",
           115.0, 128.0, 4.0, 21.5, (116.0, 4.5, 127.5, 21.0), "Asia/Manila", "Manila",
           [("Manila", 14.60, 120.98), ("Cebu", 10.32, 123.89), ("Davao", 7.19, 125.46), ("Iloilo", 10.72, 122.56),
            ("Puerto Princesa", 9.74, 118.74), ("Legazpi", 13.14, 123.74), ("Tacloban", 11.24, 125.00),
            ("Baguio", 16.40, 120.60), ("Zamboanga", 6.92, 122.08)]),
    Region("australia", "Australia", "Wind, rain and clouds over Australia and its coasts, from Darwin to Hobart.",
           110.0, 156.0, -45.0, -9.0, (112.0, -44.0, 155.0, -10.0), "Australia/Sydney", "Sydney",
           [("Sydney", -33.87, 151.21), ("Melbourne", -37.81, 144.96), ("Brisbane", -27.47, 153.03),
            ("Perth", -31.95, 115.86), ("Adelaide", -34.93, 138.60), ("Hobart", -42.88, 147.33),
            ("Darwin", -12.46, 130.84), ("Cairns", -16.92, 145.77), ("Gold Coast", -28.02, 153.40)]),
    Region("new-zealand", "New Zealand", "Wind, rain and clouds over New Zealand and the Tasman Sea's eastern side.",
           165.0, 179.5, -48.0, -33.5, (166.0, -47.5, 179.0, -34.0), "Pacific/Auckland", "Auckland",
           [("Auckland", -36.85, 174.76), ("Wellington", -41.29, 174.78), ("Christchurch", -43.53, 172.64),
            ("Dunedin", -45.88, 170.50), ("Tauranga", -37.69, 176.17), ("Napier", -39.49, 176.91),
            ("Nelson", -41.27, 173.28), ("Invercargill", -46.41, 168.35), ("Gisborne", -38.66, 178.02)]),
    Region("canada", "Canada", "Wind, rain and clouds over southern Canada, from the Pacific coast to Newfoundland.",
           -140.0, -52.0, 41.5, 61.0, (-136.0, 42.0, -53.0, 60.0), "America/Toronto", "Toronto",
           [("Vancouver", 49.28, -123.12), ("Victoria", 48.43, -123.37), ("Toronto", 43.65, -79.38),
            ("Montreal", 45.50, -73.57), ("Halifax", 44.65, -63.57), ("St. John's", 47.56, -52.71),
            ("Quebec City", 46.81, -71.21), ("Prince Rupert", 54.32, -130.32), ("Charlottetown", 46.24, -63.13),
            ("Winnipeg", 49.90, -97.14)]),
    Region("south-africa", "South Africa", "Wind, rain and clouds over South Africa's coasts, from the Atlantic to the Indian Ocean.",
           14.0, 34.0, -36.5, -26.0, (15.0, -36.0, 33.5, -27.0), "Africa/Johannesburg", "Cape Town",
           [("Cape Town", -33.92, 18.42), ("Durban", -29.86, 31.02), ("Gqeberha", -33.96, 25.60),
            ("East London", -33.02, 27.91), ("Mossel Bay", -34.18, 22.15), ("Richards Bay", -28.78, 32.04),
            ("Hermanus", -34.42, 19.24), ("Saldanha", -33.01, 17.94), ("Knysna", -34.04, 23.05)]),
]


@dataclass(frozen=True)
class RegionGrid:
    """Every second source node inside a region's bounds; row 0 at the north."""
    w: int
    h: int
    i0: int  # source column of the west edge (may exceed the row length: it wraps)
    j0: int  # source row of the north edge (source rows run northward)
    sg: SourceGrid

    @classmethod
    def of(cls, region: Region, sg: SourceGrid) -> "RegionGrid":
        i0 = math.ceil((region.west - sg.lon0) / sg.dlon - EPS)
        w = int(math.floor(((region.east - sg.lon0) / sg.dlon + EPS - i0) / STEP)) + 1
        j_south = math.ceil((region.south - sg.lat0) / sg.dlat - EPS)
        h = int(math.floor(((region.north - sg.lat0) / sg.dlat + EPS - j_south) / STEP)) + 1
        return cls(w=w, h=h, i0=i0, j0=j_south + STEP * (h - 1), sg=sg)

    def cols(self) -> np.ndarray:
        return self.i0 + STEP * np.arange(self.w)

    def rows(self) -> np.ndarray:
        """Source rows, north to south."""
        return self.j0 - STEP * np.arange(self.h)

    def lons(self) -> np.ndarray:
        lon = self.sg.lon0 + self.cols() * self.sg.dlon
        return np.where(lon > 180 + EPS, lon - 360, lon)

    def lats(self) -> np.ndarray:
        return self.sg.lat0 + self.rows() * self.sg.dlat

    @property
    def north(self) -> float:
        return float(self.lats()[0])

    @property
    def south(self) -> float:
        return float(self.lats()[-1])

    @property
    def west(self) -> float:
        return float(self.lons()[0])

    @property
    def east(self) -> float:
        return float(self.lons()[-1])

    def manifest_fields(self) -> dict:
        return {"w": self.w, "h": self.h, "north": self.north, "south": self.south,
                "west": self.west, "east": self.east}


def sample(field: np.ndarray, rg: RegionGrid) -> np.ndarray:
    """The source field at the regional nodes (h x w, north first), x wrapped. The reference's
    hourly wind peaks match this node reading exactly (phase 6)."""
    return field[np.ix_(rg.rows(), rg.cols() % field.shape[1])].astype(np.float32)


def smooth151(x: np.ndarray) -> np.ndarray:
    """Separable [1, 5, 1] / 7 on a regional grid, edges clamped (the regional rain rule, fitted
    to the reference's hourly rain peaks: bias +0.04 mm/h)."""
    p = np.pad(x, 1, mode="edge")
    x = (p[1:-1, :-2] + 5 * p[1:-1, 1:-1] + p[1:-1, 2:]) / 7
    p = np.pad(x, 1, mode="edge")
    return ((p[:-2, 1:-1] + 5 * p[1:-1, 1:-1] + p[2:, 1:-1]) / 7).astype(np.float32)


def region_peak(f: np.ndarray, rg: RegionGrid) -> list[float]:
    """[value (1 dp), lat (2 dp), lon (2 dp)] of the regional cell with the highest value."""
    if not np.isfinite(f).any():
        return [0.0, 0.0, 0.0]
    y, x = np.unravel_index(np.nanargmax(f), f.shape)
    return [round(float(f[y, x]), 1), round(float(rg.lats()[y]), 2), round(float(rg.lons()[x]), 2)]
