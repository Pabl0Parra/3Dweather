"""Base map files built once from Natural Earth (public domain): land mask, coastline and the
regional maps' land and coast outlines."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw

from .sources.openmeteo import http_fetch

NATURAL_EARTH = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson"
LAND = "ne_50m_land.geojson"
COAST = "ne_50m_coastline.geojson"
GLACIATED = "ne_50m_glaciated_areas.geojson"
SOURCE = "Natural Earth 1:50m v5.1.2 (public domain)"


def _polygons(geojson: dict):
    for feature in geojson["features"]:
        geom = feature["geometry"]
        if geom["type"] == "Polygon":
            yield geom["coordinates"]
        elif geom["type"] == "MultiPolygon":
            yield from geom["coordinates"]


def _lines(geojson: dict):
    for feature in geojson["features"]:
        geom = feature["geometry"]
        if geom["type"] == "LineString":
            yield geom["coordinates"]
        elif geom["type"] == "MultiLineString":
            yield from geom["coordinates"]


def rasterize_land(geojson: dict, w: int = 2048, h: int = 1024) -> Image.Image:
    """Equirectangular mask: 255 land, 0 sea. Row 0 is 90 N, column 0 is 180 W."""
    img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(img)

    def xy(ring):
        return [((lon + 180.0) / 360.0 * w, (90.0 - lat) / 180.0 * h) for lon, lat, *_ in ring]

    for rings in _polygons(geojson):
        draw.polygon(xy(rings[0]), fill=255)
        for hole in rings[1:]:
            draw.polygon(xy(hole), fill=0)
    return img


def coast_lines(geojson: dict) -> list[list[float]]:
    """One flat [lon, lat, lon, lat, ...] list per line, 2 decimals, no repeated points."""
    out = []
    for line in _lines(geojson):
        flat: list[float] = []
        for lon, lat, *_ in line:
            point = [round(float(lon), 2), round(float(lat), 2)]
            if flat[-2:] != point:
                flat += point
        if len(flat) >= 4:
            out.append(flat)
    return out


Box = tuple[float, float, float, float]  # west, south, east, north


def _flat(points, nd: int = 3) -> list[float]:
    flat: list[float] = []
    for lon, lat in points:
        p = [round(float(lon), nd), round(float(lat), nd)]
        if flat[-2:] != p:
            flat += p
    return flat


def clip_ring(ring, box: Box) -> list[float]:
    """Sutherland-Hodgman clip of a polygon ring to a box; flat [lon, lat, ...], [] if nothing is left."""
    w, s, e, n = box
    pts = [(float(p[0]), float(p[1])) for p in ring]
    edges = [(lambda p: p[0] >= w, lambda a, b: (w, a[1] + (b[1] - a[1]) * (w - a[0]) / (b[0] - a[0]))),
             (lambda p: p[0] <= e, lambda a, b: (e, a[1] + (b[1] - a[1]) * (e - a[0]) / (b[0] - a[0]))),
             (lambda p: p[1] >= s, lambda a, b: (a[0] + (b[0] - a[0]) * (s - a[1]) / (b[1] - a[1]), s)),
             (lambda p: p[1] <= n, lambda a, b: (a[0] + (b[0] - a[0]) * (n - a[1]) / (b[1] - a[1]), n))]
    for inside, cut in edges:
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cut(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cut(prev, cur))
        pts = out
        if not pts:
            return []
    flat = _flat(pts)
    return flat if len(flat) >= 6 else []


def clip_line(line, box: Box) -> list[list[float]]:
    """Runs of a polyline whose segments touch the box (end points just outside are kept, so a
    line reaching the edge is drawn to it); flat [lon, lat, ...] per run."""
    w, s, e, n = box
    pts = [(float(p[0]), float(p[1])) for p in line]
    runs, cur = [], []
    for a, b in zip(pts, pts[1:]):
        touches = max(a[0], b[0]) >= w and min(a[0], b[0]) <= e and max(a[1], b[1]) >= s and min(a[1], b[1]) <= n
        if touches:
            if not cur:
                cur = [a]
            cur.append(b)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return [f for f in (_flat(r) for r in runs) if len(f) >= 4]


def region_land(land: dict, coast: dict, region) -> dict:
    """Land polygons (outer ring then holes) and coastlines clipped to a region's grid plus one cell."""
    pad = 0.25
    box = (round(region.west - pad, 3), round(region.south - pad, 3), round(region.east + pad, 3), round(region.north + pad, 3))
    polys = []
    for rings in _polygons(land):
        outer = clip_ring(rings[0], box)
        if outer:
            polys.append([outer] + [h for h in (clip_ring(r, box) for r in rings[1:]) if h])
    lines = [run for line in _lines(coast) for run in clip_line(line, box)]
    return {"region": region.slug, "source": SOURCE, "west": box[0], "south": box[1], "east": box[2], "north": box[3],
            "land": polys, "coast": lines}


def _load(name: str, cache_dir: Path, fetch: Callable[[str, Path], None]) -> dict:
    path = cache_dir / name
    if not path.exists():
        fetch(f"{NATURAL_EARTH}/{name}", path)
    return json.loads(path.read_text(encoding="utf-8"))


def build_static(cache_dir: Path, out_dir: Path, fetch: Callable[[str, Path], None] = http_fetch) -> None:
    cache_dir, out_dir = Path(cache_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mask = out_dir / "land-mask.png"
    rasterize_land(_load(LAND, cache_dir, fetch)).save(mask.with_name(mask.name + ".part"), format="PNG", optimize=True)
    mask.with_name(mask.name + ".part").replace(mask)
    coast = out_dir / "coast.json"
    coast.with_name(coast.name + ".part").write_text(
        json.dumps({"source": SOURCE, "lines": coast_lines(_load(COAST, cache_dir, fetch))}, separators=(",", ":")))
    coast.with_name(coast.name + ".part").replace(coast)
    from .regions import REGIONS
    land, lines = _load(LAND, cache_dir, fetch), _load(COAST, cache_dir, fetch)
    (out_dir / "regions").mkdir(exist_ok=True)
    for r in REGIONS:
        path = out_dir / "regions" / f"{r.slug}.json"
        path.with_name(path.name + ".part").write_text(
            json.dumps(region_land(land, lines, r), separators=(",", ":")), encoding="utf-8")
        path.with_name(path.name + ".part").replace(path)


def ice_mask(cache_dir: Path, fetch: Callable[[str, Path], None] = http_fetch) -> np.ndarray:
    """Globe cells (384 x 768, bool) covered by glaciers and ice sheets. The reference's
    "coldest place" leaves these out (matched at every hour of run 2026111306)."""
    from .grid import GLOBE
    img = rasterize_land(_load(GLACIATED, Path(cache_dir), fetch), GLOBE.w, GLOBE.h)
    return np.asarray(img) >= 128
