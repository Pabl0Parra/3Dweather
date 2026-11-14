from datetime import datetime, timedelta, timezone

import numpy as np
from PIL import Image

from pipeline.ocean import CURRENT_EVERY, CURRENT_FRAMES, ocean_frame, ocean_time, pack_ocean
from pipeline.regrid import SourceGrid

SG = SourceGrid(lat0=-90.0, lon0=-180.0, dlat=1.0, dlon=1.0)
T = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)


def test_frames_are_daily_snapshots_at_the_globe_run_hour():
    assert CURRENT_FRAMES == 8 and CURRENT_EVERY == 24
    assert ocean_time(T, 0) == T and ocean_time(T, 7) == T + timedelta(hours=168)


def test_land_is_filled_near_coast_and_none_inland():
    u = np.full((181, 360), 1.0, np.float32)
    u[:, 100:200] = np.nan  # a wide continent
    v = np.zeros_like(u)
    sst = np.full_like(u, 20.0)
    sst[:, 100:200] = np.nan
    f = ocean_frame(u, v, sst, SG)
    assert f.shape == (384, 768, 3) and f.dtype == np.uint8
    inland = f[192, 320]  # lon -30 in the globe = column ~320, source column 150: deep inland
    assert inland[0] == 128 and inland[2] == 0
    coast = f[192, 213]  # just inside the coast at lon ~80 W (source column 100)
    assert coast[0] > 128 and coast[2] > 0


def test_eight_frames_four_by_two():
    frames = [np.full((384, 768, 3), k, np.uint8) for k in range(8)]
    img = pack_ocean(frames)
    assert isinstance(img, Image.Image) and img.size == (4 * 768, 2 * 384)
    assert np.asarray(img)[384, 768, 0] == 5  # frame 5 at column 1, row 1
