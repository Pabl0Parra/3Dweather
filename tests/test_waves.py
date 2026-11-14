from datetime import datetime, timezone

import numpy as np

from pipeline.sources.openmeteo import MODELS
from pipeline.waves import fill_land, frame_time, wave_frame, wave_peak

SG = MODELS["ncep_gfswave025"]


def test_fill_land_extends_coast_only():
    f = np.full((10, 10), np.nan, np.float32)
    f[:, 0] = 2.0
    out = fill_land(f, passes=4)
    # 4 passes reach columns 1-4 directly and 9-6 through the longitude wrap; column 5 stays empty
    assert np.allclose(out[:, 1:5], 2.0) and np.isnan(out[:, 5]).all() and (out[:, 0] == 2.0).all()


def test_wave_frame_channels():
    h = np.full((721, 1440), 9.0, np.float32)
    f = wave_frame(h, np.full_like(h, 10.0), np.full_like(h, 270.0), SG)
    assert f.shape == (384, 768, 3) and f.dtype == np.uint8
    assert (f[..., 0] == 191).all()  # sqrt(9/16)*255 = 191.25
    assert (f[..., 1] == 179).all() and (f[..., 2] == 128).all()  # east, length 0.4 -> 128 + 50.8


def test_direction_seam_does_not_cancel():
    h = np.ones((721, 1440), np.float32)
    d = np.where(np.arange(1440)[None, :] % 2 == 0, 359.0, 1.0).astype(np.float32) + np.zeros_like(h)
    f = wave_frame(h, np.full_like(h, 25.0), d, SG)
    assert (f[..., 2] <= 2).all()  # still travelling south at nearly full length


def test_all_land_cell_encodes_as_empty():
    h = np.full((721, 1440), np.nan, np.float32)
    f = wave_frame(h, h, h, SG)
    assert (f[..., 0] == 0).all() and (f[..., 1] == 128).all() and (f[..., 2] == 128).all()


def test_wave_peak_snaps_to_globe_cell():
    h = np.zeros((721, 1440), np.float32)
    h[537, 156] = 13.88  # 44.25 N, 141.0 W
    assert wave_peak(h, SG) == [13.9, 44.28, -140.92]


def test_frame_time_steps_three_hours():
    run = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)
    assert frame_time(run, 56) == datetime(2026, 11, 20, 6, tzinfo=timezone.utc)
