import re

import numpy as np
import pytest

from pipeline.regions import REGIONS, RegionGrid, region_peak, sample
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


@pytest.mark.parametrize("rule", ["point", "tent"])
def test_constant_field_samples_exactly(rule):
    field = np.full((181, 360), 7.5, np.float32)
    out = sample(field, SG, RegionGrid.of(small(-10, 10, 40, 50), SG), rule)
    assert out.shape == (6, 11) and np.allclose(out, 7.5)


def test_spike_lands_on_its_cell_and_tent_spreads_it():
    field = np.zeros((181, 360), np.float32)
    field[90 + 46, 180 - 6] = 16.0  # node lat 46, lon -6
    g = RegionGrid.of(small(-10, 10, 40, 50), SG)
    point = sample(field, SG, g, "point")
    assert point[2, 2] == 16.0 and point.sum() == 16.0  # row 2 = lat 46, col 2 = lon -6
    tent = sample(field, SG, g, "tent")
    assert tent[2, 2] == pytest.approx(4.0)  # centre weight 2*2 / (4*4)


def test_tent_ignores_missing_neighbours():
    field = np.full((181, 360), 3.0, np.float32)
    field[90 + 46, 180 - 5] = np.nan
    out = sample(field, SG, RegionGrid.of(small(-10, 10, 40, 50), SG), "tent")
    assert np.isfinite(out).all() and np.allclose(out, 3.0)


def test_longitude_wraps_past_the_last_node():
    field = np.zeros((181, 360), np.float32)
    field[:, 0] = 5.0  # lon -180 == lon 180
    g = RegionGrid.of(small(170, 180, 40, 50), SG)
    out = sample(field, SG, g, "point")
    assert g.east == 180 and np.allclose(out[:, -1], 5.0)
    assert np.allclose(sample(field, SG, g, "tent")[:, -1], 5.0 * 2 / 4)


def test_region_peak_reports_value_and_position():
    g = RegionGrid.of(small(-10, 10, 40, 50), SG)
    f = np.zeros((g.h, g.w), np.float32)
    f[2, 2] = 12.345
    assert region_peak(f, g) == [12.3, 46.0, -6.0]
    assert region_peak(np.full((g.h, g.w), np.nan), g) == [0.0, 0.0, 0.0]
