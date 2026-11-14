import numpy as np

from pipeline.grid import GLOBE
from pipeline.peaks import hourly, peak


def test_hourly_repeats_each_frame():
    frames = [[float(j), 0.0, 0.0] for j in range(57)]
    out = hourly(frames, every=3, hours=168)
    assert len(out) == 169 and out[0] == out[2] == frames[0] and out[3] == frames[1] and out[168] == frames[56]


def test_daily_frames_and_gust_series():
    assert hourly([[k, 0, 0] for k in range(8)], every=24, hours=168)[167][0] == 6
    assert len(hourly([[j, 0, 0] for j in range(29)], every=3, hours=84)) == 85


def test_max_and_min_peaks():
    a = np.zeros((GLOBE.h, GLOBE.w), np.float32)
    a[100, 200], a[300, 50] = 7.25, -3.0
    assert peak(a) == [7.2, round(float(GLOBE.lats()[100]), 2), round(float(GLOBE.lons()[200]), 2)] or \
        peak(a)[0] == 7.3
    assert peak(a, mode="min")[0] == -3.0 and peak(a, mode="min")[1] == round(float(GLOBE.lats()[300]), 2)


def test_peak_reports_true_value_beyond_byte_scale():
    a = np.full((GLOBE.h, GLOBE.w), 1000.0, np.float32)
    a[10, 10] = 935.3
    assert peak(a, mode="min")[0] == 935.3


def test_all_missing_is_zero():
    assert peak(np.full((GLOBE.h, GLOBE.w), np.nan, np.float32)) == [0.0, 0.0, 0.0]


def test_masked_cells_are_left_out():
    a = np.zeros((GLOBE.h, GLOBE.w), np.float32)
    a[10, 10], a[200, 300] = -50.0, -30.0
    mask = np.zeros_like(a, dtype=bool)
    mask[10, 10] = True
    assert peak(a, mode="min", exclude=mask)[0] == -30.0
