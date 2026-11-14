import json
from pathlib import Path

from pipeline.static_assets import build_static, coast_lines, rasterize_land

SQUARE_WITH_HOLE = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
    "geometry": {"type": "Polygon", "coordinates": [
        [[-10, -10], [10, -10], [10, 10], [-10, 10], [-10, -10]],
        [[-2, -2], [2, -2], [2, 2], [-2, 2], [-2, -2]]]}}]}

TWO_SQUARES = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
    "geometry": {"type": "MultiPolygon", "coordinates": [
        [[[20, 20], [30, 20], [30, 30], [20, 30], [20, 20]]],
        [[[-30, -30], [-20, -30], [-20, -20], [-30, -20], [-30, -30]]]]}}]}

LINES = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {}, "geometry":
        {"type": "LineString", "coordinates": [[1.234, 5.678], [1.2341, 5.6779], [3, 4]]}},
    {"type": "Feature", "properties": {}, "geometry": {"type": "LineString", "coordinates": [[0, 0]]}}]}


def px(img, lat, lon):
    w, h = img.size
    return img.getpixel((int((lon + 180) / 360 * w), int((90 - lat) / 180 * h)))


def test_land_mask_fills_polygon_and_keeps_holes():
    img = rasterize_land(SQUARE_WITH_HOLE, 360, 180)
    assert img.mode == "L" and img.size == (360, 180)
    assert px(img, 6, 6) == 255 and px(img, 0, 0) == 0 and px(img, 30, 30) == 0


def test_multipolygon_supported():
    img = rasterize_land(TWO_SQUARES, 360, 180)
    assert px(img, 25, 25) == 255 and px(img, -25, -25) == 255 and px(img, 0, 0) == 0


def test_coast_lines_are_flat_rounded_and_deduplicated():
    assert coast_lines(LINES) == [[1.23, 5.68, 3.0, 4.0]]


def test_multilinestring_supported():
    gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry":
          {"type": "MultiLineString", "coordinates": [[[0, 0], [1, 1]], [[2, 2], [3, 3]]]}}]}
    assert coast_lines(gj) == [[0.0, 0.0, 1.0, 1.0], [2.0, 2.0, 3.0, 3.0]]


def test_build_static_writes_both_files(tmp_path):
    served = {"ne_50m_land.geojson": SQUARE_WITH_HOLE, "ne_50m_coastline.geojson": LINES}
    calls = []

    def fetch(url: str, dest: Path) -> None:
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(served[url.rsplit("/", 1)[1]]))

    build_static(tmp_path / "cache", tmp_path / "out", fetch=fetch)
    from PIL import Image
    img = Image.open(tmp_path / "out" / "land-mask.png")
    assert img.size == (2048, 1024) and px(img, 6, 6) == 255
    coast = json.loads((tmp_path / "out" / "coast.json").read_text())
    assert coast["lines"] == [[1.23, 5.68, 3.0, 4.0]] and "Natural Earth" in coast["source"]
    assert all(u.startswith("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/")
               for u in calls)
    build_static(tmp_path / "cache", tmp_path / "out", fetch=fetch)  # second run uses the cache
    assert len(calls) == 2
