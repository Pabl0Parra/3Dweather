import warnings

import pytest

import numpy as np

from pipeline.grid import GLOBE
from pipeline.regrid import SourceGrid, regrid_bilinear

SG = SourceGrid(lat0=-90.0, lon0=-180.0, dlat=0.25, dlon=0.25)
LAT = -90 + 0.25 * np.arange(721)[:, None] + np.zeros((1, 1440))
LON = -180 + 0.25 * np.arange(1440)[None, :] + np.zeros((721, 1))


def test_linear_field_is_reproduced():
    out = regrid_bilinear(LAT.astype(np.float32), SG, GLOBE)
    assert out.shape == (384, 768)
    assert np.allclose(out[:, 5], GLOBE.lats(), atol=1e-3)


def test_wraps_across_antimeridian():
    out = regrid_bilinear(np.cos(np.radians(LON)).astype(np.float32), SG, GLOBE)
    assert np.isfinite(out).all()
    assert np.allclose(out[100, [0, 767]], np.cos(np.radians(GLOBE.lons()[[0, 767]])), atol=1e-3)


def test_missing_cells_are_ignored_not_spread():
    src = np.ones((721, 1440), np.float32)
    src[300:340, 500:560] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # no divide-by-zero warnings
        out = regrid_bilinear(src, SG, GLOBE)
    y, x = GLOBE.cell_of(-90 + 0.25 * 320, -180 + 0.25 * 530)
    assert np.isnan(out[y, x])  # all four neighbours missing
    assert np.allclose(out[np.isfinite(out)], 1.0, atol=1e-6)  # partial neighbours use valid ones only


# --- reduced Gaussian (IFS O1280) ---
from pipeline.grid import GLOBE
from pipeline.regrid import ReducedGaussian, regrid

O1280 = ReducedGaussian(1280)


def _points(rg):
    lats = np.repeat(rg.lats(), rg.counts())
    lons = np.concatenate([np.arange(c) * 360.0 / c for c in rg.counts()])
    return np.radians(lats), np.radians(lons)


def _f(lat, lon):
    return np.sin(lat) + np.cos(lat) * np.cos(lon - np.radians(30))


@pytest.fixture(scope="module")
def smooth():
    lat, lon = _points(O1280)
    src = _f(lat, lon)[None, :].astype(np.float32)
    want = _f(np.radians(GLOBE.lats())[:, None], np.radians(GLOBE.lons())[None, :])
    return src, want


def test_o1280_has_6599680_points():
    assert int(np.sum(O1280.counts())) == 6599680
    assert len(O1280.lats()) == 2560 and O1280.lats()[0] > 89 and O1280.lats()[-1] < -89


def test_smooth_field_is_reproduced(smooth):
    src, want = smooth
    assert np.nanmax(np.abs(regrid(src, O1280, GLOBE) - want)) < 1e-3


def test_no_seam_at_antimeridian(smooth):
    out = regrid(smooth[0], O1280, GLOBE)
    assert np.max(np.abs(out[:, 0] - out[:, -1])) < 0.02


def test_poles_are_finite(smooth):
    out = regrid(smooth[0], O1280, GLOBE)
    assert np.isfinite(out[0]).all() and np.isfinite(out[-1]).all()


def test_missing_cells_are_skipped(smooth):
    src, want = smooth
    src = src.copy()
    start = int(np.sum(O1280.counts()[:1000]))
    src[0, start:start + O1280.counts()[1000]] = np.nan
    out = regrid(src, O1280, GLOBE)
    assert np.isfinite(out).all() and np.max(np.abs(out - want)) < 0.01


# --- block (area) mean: the globe grid is exactly 4x4 GFS 13 km cells ---
from pipeline.regrid import regrid_block_mean
from pipeline.sources.openmeteo import MODELS

GFS13 = MODELS["ncep_gfs013"]


def test_block_mean_averages_four_by_four():
    src = np.zeros((1536, 3072), np.float32)
    src[1532:1536, 0:4] = 1.0  # the top-left globe cell's block (rows run northward)
    src[1532:1536, 4] = 8.0  # one column of the next block
    out = regrid(src, GFS13, GLOBE)
    assert out.shape == (384, 768)
    assert out[0, 0] == 1.0 and out[0, 1] == 2.0 and out[1, 0] == 0.0


def test_block_mean_rejects_misaligned_grids():
    with pytest.raises(ValueError):
        regrid_block_mean(np.zeros((721, 1440)), SG, GLOBE)
