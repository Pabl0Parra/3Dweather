"""Base map files built once from Natural Earth (public domain): land mask and coastline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from .sources.openmeteo import http_fetch

NATURAL_EARTH = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson"
LAND = "ne_50m_land.geojson"
COAST = "ne_50m_coastline.geojson"
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
