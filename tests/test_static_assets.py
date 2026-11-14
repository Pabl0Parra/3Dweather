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


def test_ice_mask_on_the_globe_grid(tmp_path):
    from pipeline.static_assets import GLACIATED, ice_mask
    square = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {
        "type": "Polygon", "coordinates": [[[-50, 60], [-30, 60], [-30, 80], [-50, 80], [-50, 60]]]}}]}
    (tmp_path / GLACIATED).write_text(__import__("json").dumps(square), encoding="utf-8")
    m = ice_mask(tmp_path, fetch=lambda url, dest: (_ for _ in ()).throw(AssertionError("no fetch")))
    assert m.shape == (384, 768) and m.dtype == bool
    from pipeline.grid import GLOBE
    assert m[GLOBE.cell_of(70, -40)] and not m[GLOBE.cell_of(70, 0)]


# --- regional outlines (phase 6) ---

from pipeline.static_assets import clip_line, clip_ring, region_land  # noqa: E402


def area(flat):
    xs, ys = flat[0::2], flat[1::2]
    return abs(sum(xs[i] * ys[(i + 1) % len(xs)] - xs[(i + 1) % len(xs)] * ys[i] for i in range(len(xs)))) / 2


def test_clip_ring_keeps_the_part_inside():
    ring = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    out = clip_ring(ring, (5, -5, 15, 15))  # west, south, east, north
    assert area(out) == 50 and min(out[0::2]) == 5


def test_clip_ring_drops_a_ring_outside():
    assert clip_ring([[0, 0], [1, 0], [1, 1], [0, 0]], (5, 5, 6, 6)) == []


def test_clip_line_keeps_runs_that_touch_the_box():
    line = [[0, 0], [4, 0], [6, 0], [8, 0], [20, 0], [30, 0]]
    assert clip_line(line, (5, -1, 7, 1)) == [[4.0, 0.0, 6.0, 0.0, 8.0, 0.0]]
    assert clip_line([[0, 0], [1, 1]], (5, 5, 6, 6)) == []


def test_region_land_clips_to_the_grid_plus_a_cell():
    from pipeline.regions import REGIONS
    eu = next(r for r in REGIONS if r.slug == "europe")
    land = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [
            [[0, 40], [10, 40], [10, 50], [0, 50], [0, 40]], [[4, 44], [6, 44], [6, 46], [4, 46], [4, 44]]]}},
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [  # far away
            [[100, -10], [110, -10], [110, 0], [100, -10]]]}}]}
    coast = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry":
             {"type": "LineString", "coordinates": [[1.23456, 45.67891], [1.23456, 45.67891], [3, 44]]}}]}
    out = region_land(land, coast, eu)
    assert out["region"] == "europe" and "Natural Earth" in out["source"]
    assert out["west"] == round(eu.west - 0.25, 3) and out["north"] == round(eu.north + 0.25, 3)
    assert len(out["land"]) == 1 and len(out["land"][0]) == 2  # outer ring and its hole; the far one dropped
    assert area(out["land"][0][0]) == 100
    assert out["coast"] == [[1.235, 45.679, 3.0, 44.0]]  # 3 decimals, repeated point dropped


def test_build_static_writes_a_land_file_per_region(tmp_path):
    from pipeline.regions import REGIONS
    served = {"ne_50m_land.geojson": SQUARE_WITH_HOLE, "ne_50m_coastline.geojson": LINES}

    def fetch(url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(served[url.rsplit("/", 1)[1]]))

    build_static(tmp_path / "cache", tmp_path / "out", fetch=fetch)
    for r in REGIONS:
        data = json.loads((tmp_path / "out" / "regions" / f"{r.slug}.json").read_text(encoding="utf-8"))
        assert data["region"] == r.slug
