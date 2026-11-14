import re

import numpy as np
import pytest

from pipeline.regions import REGIONS, RegionGrid, region_peak, sample, smooth151
from pipeline.regrid import SourceGrid
from pipeline.sources.openmeteo import MODELS

GFS = MODELS["ncep_gfs013"]
SLUGS = ["united-states", "united-kingdom", "scotland", "ireland", "europe", "india", "west-pacific",
         "philippines", "australia", "new-zealand", "canada", "south-africa"]


def by_slug(slug):
    return next(r for r in REGIONS if r.slug == slug)


def test_twelve_regions_in_order():
    assert [r.slug for r in REGIONS] == SLUGS


def test_europe_grid_matches_the_reference_manifest():
    g = RegionGrid.of(by_slug("europe"), GFS)
    assert (g.w, g.h) == (350, 167)
    assert g.north == pytest.approx(71.9882746742671, abs=1e-9)
    assert g.south == pytest.approx(33.09469096091206, abs=1e-9)
    assert g.west == pytest.approx(-39.9609375, abs=1e-9)
    assert g.east == pytest.approx(41.8359375, abs=1e-9)
    assert g.lats()[0] == pytest.approx(g.north) and g.lats()[-1] == pytest.approx(g.south)
    assert g.lons()[1] - g.lons()[0] == pytest.approx(0.234375)


@pytest.mark.parametrize("slug", SLUGS)
def test_region_catalogue_is_consistent(slug):
    r = by_slug(slug)
    g = RegionGrid.of(r, GFS)
    assert -180 <= r.west < r.east <= 180 and -90 < r.south < r.north < 90  # none crosses the antimeridian
    assert 40 <= g.w <= 450 and 25 <= g.h <= 260, (g.w, g.h)  # small regions keep their seas for context
    fw, fs, fe, fn = r.focus
    assert g.west <= fw < fe <= g.east and g.south <= fs < fn <= g.north
    assert re.fullmatch(r"[A-Z][A-Za-z_]+/[A-Za-z_/]+", r.tz)
    assert len(r.cities) >= 6
    for name, lat, lon in r.cities:
        assert g.south <= lat <= g.north and g.west <= lon <= g.east, (slug, name)
    assert r.place in [c[0] for c in r.cities]
    assert r.title and r.description


SG = SourceGrid(lat0=-90.0, lon0=-180.0, dlat=1.0, dlon=1.0)  # 181 x 360 nodes


def small(west, east, south, north):
    from pipeline.regions import Region
    return Region("t", "T", "d", west, east, south, north, (west, south, east, north), "Etc/UTC", "A",
                  [("A", south, west)])


def test_grid_takes_every_second_node():
    g = RegionGrid.of(small(-10, 10, 40, 50), SG)
    assert (g.w, g.h) == (11, 6) and g.west == -10 and g.east == 10 and g.north == 50 and g.south == 40
    assert list(g.lons()[:3]) == [-10, -8, -6] and list(g.lats()[:2]) == [50, 48]


def test_constant_field_samples_exactly():
    field = np.full((181, 360), 7.5, np.float32)
    out = sample(field, RegionGrid.of(small(-10, 10, 40, 50), SG))
    assert out.shape == (6, 11) and np.allclose(out, 7.5)


def test_spike_lands_on_its_cell():
    field = np.zeros((181, 360), np.float32)
    field[90 + 46, 180 - 6] = 16.0  # node lat 46, lon -6
    out = sample(field, RegionGrid.of(small(-10, 10, 40, 50), SG))
    assert out[2, 2] == 16.0 and out.sum() == 16.0  # row 2 = lat 46, col 2 = lon -6


def test_longitude_wraps_past_the_last_node():
    field = np.zeros((181, 360), np.float32)
    field[:, 0] = 5.0  # lon -180 == lon 180
    g = RegionGrid.of(small(170, 180, 40, 50), SG)
    assert g.east == 180 and np.allclose(sample(field, g)[:, -1], 5.0)


def test_smooth151_keeps_constants_and_spreads_a_spike():
    assert np.allclose(smooth151(np.full((5, 6), 3.0)), 3.0)
    x = np.zeros((5, 5))
    x[2, 2] = 49.0
    y = smooth151(x)
    assert y[2, 2] == pytest.approx(25.0) and y[2, 3] == pytest.approx(5.0) and y[1, 1] == pytest.approx(1.0)
    assert y.sum() == pytest.approx(49.0)


def test_region_peak_reports_value_and_position():
    g = RegionGrid.of(small(-10, 10, 40, 50), SG)
    f = np.zeros((g.h, g.w), np.float32)
    f[2, 2] = 12.345
    assert region_peak(f, g) == [12.3, 46.0, -6.0]
    assert region_peak(np.full((g.h, g.w), np.nan), g) == [0.0, 0.0, 0.0]


def test_web_region_list_matches_the_pipeline():
    """web/src/region/regions.ts builds the pages; it must name the same regions as the pipeline."""
    import json as _json
    from pathlib import Path
    ts = (Path(__file__).resolve().parent.parent / "web" / "src" / "region" / "regions.ts").read_text(encoding="utf-8")
    rows = re.findall(r'slug: ("[^"]*"), title: ("[^"]*"), tz: ("[^"]*"),\s*description: ("[^"]*")', ts)
    assert [(_json.loads(s), _json.loads(t), _json.loads(z), _json.loads(d)) for s, t, z, d in rows] == \
        [(r.slug, r.title, r.tz, r.description) for r in REGIONS]
