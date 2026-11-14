import warnings

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
