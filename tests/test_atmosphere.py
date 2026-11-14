from datetime import datetime, timedelta, timezone

import numpy as np

from pipeline.atmosphere import (cloud_from_layers, frame_a, frame_b, frame_t, rain_rate, smooth141)

SHAPE = (384, 768)
T = datetime(2026, 11, 13, 6, tzinfo=timezone.utc)


def full(v):
    return np.full(SHAPE, v, np.float32)


def test_wind_channels_encode_u_and_v():
    f = frame_a({"u": full(10), "v": full(-5), "rain": full(0)})
    assert f.dtype == np.uint8 and f.shape == (384, 768, 3)
    assert (f[..., 0] == 153).all() and (f[..., 1] == 115).all() and (f[..., 2] == 0).all()


def test_missing_rain_and_cloud_encode_none():
    a = frame_a({"u": full(0), "v": full(0), "rain": None})
    b = frame_b({"cloud": None, "pressure": full(1000), "gust": full(10)})
    assert (a[..., 2] == 0).all() and (b[..., 0] == 0).all() and (b[..., 1] > 0).all()


def test_gust_none_after_hour_84():
    b = frame_b({"cloud": full(50), "pressure": full(1000), "gust": None})
    assert (b[..., 2] == 0).all()


def test_temperature_frame():
    t = frame_t({"temp": full(15)})
    assert (t[..., 0] == 174).all() and (t[..., 1:] == 0).all()


def test_smooth141_keeps_flat_fields_and_wraps():
    assert np.allclose(smooth141(full(3)), 3)
    a = np.zeros(SHAPE)
    a[100, 0] = 36.0
    s = smooth141(a)
    assert np.isclose(s[100, 0], 16.0) and np.isclose(s[100, -1], 4.0) and np.isclose(s.sum(), 36.0)


class Steps:
    """Fake precipitation source: hourly then 3-hourly steps; hour 0 absent."""
    def __init__(self, values):  # {hour: globe-grid array or None}
        self.values = values
        self.times = [T + timedelta(hours=h) for h in sorted(values)]

    def valid_times(self):
        return self.times

    def field(self, t):
        return self.values[int((t - T).total_seconds() // 3600)]


def test_rain_rate_means_the_hour_before_and_after():
    src = Steps({0: None, 1: full(2), 2: full(4), 3: full(8)})
    assert np.allclose(rain_rate(src, T + timedelta(hours=2), smooth=False), 6.0)  # (4 + 8) / 2


def test_rain_rate_leaves_out_missing_hours():
    src = Steps({0: None, 1: full(2), 2: full(4)})
    assert np.allclose(rain_rate(src, T, smooth=False), 2.0)  # only hour (0, 1] is covered


def test_rain_rate_spreads_three_hour_steps():
    src = Steps({117: full(0), 120: full(9), 123: full(6)})  # 3-hour totals ending at 120 and 123
    # window (119, 121]: 1 h of 9/3 per hour and 1 h of 6/3 per hour
    assert np.allclose(rain_rate(src, T + timedelta(hours=120), smooth=False), 2.5)


def test_cloud_from_layers():
    assert np.allclose(cloud_from_layers(full(40), full(70), full(0)), 70)
    assert np.allclose(cloud_from_layers(full(0), full(0), full(100)), 30)
    assert np.allclose(cloud_from_layers(full(50), full(0), full(100)), 65)  # 50 + 0.3*100*0.5
