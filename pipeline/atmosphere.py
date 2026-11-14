"""Atmosphere frames: a = wind u, wind v, rain · b = cloud, pressure, gust · t = air temperature.

Rules matched against the reference run (see the phase 3a ledger and spec §9):
GFS 13 km fields are 4x4 block means; rain is the mean rate over the hour before
and after the frame, lightly smoothed; cloud is our own blend of low, mid and high.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

import numpy as np

from .codecs import (encode_air_temp, encode_cloud, encode_gust, encode_pressure, encode_rain,
                     encode_wind)
from .grid import GLOBE

Fields = dict[str, "np.ndarray | None"]
GUST_HOURS = 84
HIGH_CLOUD_WEIGHT = 0.3


def _none(shape=(GLOBE.h, GLOBE.w)) -> np.ndarray:
    return np.full(shape, np.nan, np.float32)


def _or_none(a):
    return _none() if a is None else a


def frame_a(f: Fields) -> np.ndarray:
    return np.dstack([encode_wind(f["u"]), encode_wind(f["v"]), encode_rain(_or_none(f["rain"]))])


def frame_b(f: Fields) -> np.ndarray:
    return np.dstack([encode_cloud(_or_none(f["cloud"])), encode_pressure(_or_none(f["pressure"])),
                      encode_gust(_or_none(f["gust"]))])


def frame_t(f: Fields) -> np.ndarray:
    zero = np.zeros((GLOBE.h, GLOBE.w), np.uint8)
    return np.dstack([encode_air_temp(f["temp"]), zero, zero])


def smooth141(a: np.ndarray) -> np.ndarray:
    """Separable [1, 4, 1] / 6 smoothing; columns wrap, rows clamp at the poles."""
    a = np.asarray(a, dtype=np.float64)
    a = (4 * a + np.roll(a, 1, axis=1) + np.roll(a, -1, axis=1)) / 6
    up = np.vstack([a[:1], a[:-1]])
    down = np.vstack([a[1:], a[-1:]])
    return ((4 * a + up + down) / 6).astype(np.float32)


class PrecipSteps(Protocol):
    def valid_times(self) -> list[datetime]: ...
    def field(self, t: datetime) -> np.ndarray | None: ...  # amount in the step ending at t, globe grid


def rain_rate(src: PrecipSteps, t: datetime, smooth: bool = True) -> np.ndarray | None:
    """Mean rain rate (mm/h) over the covered part of (t - 1 h, t + 1 h]. Each step's
    amount is spread evenly over its own length, so 3-hourly steps work too."""
    w0, w1 = t - timedelta(hours=1), t + timedelta(hours=1)
    times = src.valid_times()
    total, covered = None, 0.0
    for start, end in zip(times, times[1:]):
        overlap = (min(end, w1) - max(start, w0)).total_seconds() / 3600
        if overlap <= 0:
            continue
        amount = src.field(end)
        if amount is None:
            continue
        part = np.nan_to_num(amount) * (overlap / ((end - start).total_seconds() / 3600))
        total = part if total is None else total + part
        covered += overlap
    if total is None:
        return None
    rate = (total / covered).astype(np.float32)
    return smooth141(rate) if smooth else rate


def cloud_from_layers(low: np.ndarray, mid: np.ndarray, high: np.ndarray) -> np.ndarray:
    """Percent. The thicker of low and mid cloud, plus some of the high cloud in the gap."""
    m = np.maximum(low, mid)
    return (m + HIGH_CLOUD_WEIGHT * high * (1 - m / 100.0)).astype(np.float32)
