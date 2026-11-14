"""Byte encodings for the globe sprites. Must match web/src/globe/codecs.ts."""
from __future__ import annotations

import numpy as np

MAX_HEIGHT_M = 16.0
MAX_PERIOD_S = 25.0


def encode_wave_height(m: np.ndarray) -> np.ndarray:
    """Square-root scale, 0-16 m. Missing values become 0."""
    scaled = np.sqrt(np.clip(np.nan_to_num(m, nan=0.0), 0.0, MAX_HEIGHT_M) / MAX_HEIGHT_M) * 255.0
    return np.rint(scaled).astype(np.uint8)


def decode_wave_height(b: np.ndarray) -> np.ndarray:
    return (np.asarray(b, dtype=np.float64) / 255.0) ** 2 * MAX_HEIGHT_M


def wave_vector(direction_from_deg: np.ndarray, period_s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(east, north) components pointing where the waves travel; length = period / 25 s."""
    toward = np.radians(np.asarray(direction_from_deg, dtype=np.float64) + 180.0)
    length = np.clip(np.asarray(period_s, dtype=np.float64), 0.0, MAX_PERIOD_S) / MAX_PERIOD_S
    return np.sin(toward) * length, np.cos(toward) * length


def encode_vector(vx: np.ndarray, vy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """128 = zero, 1 unit = 127 steps. Missing values become 128."""
    def enc(v: np.ndarray) -> np.ndarray:
        return np.rint(128.0 + 127.0 * np.clip(np.nan_to_num(v, nan=0.0), -1.0, 1.0)).astype(np.uint8)
    return enc(vx), enc(vy)


# --- Every other globe quantity (findings §4). rint, then clip; missing -> "none". ---

def _bytes(x: np.ndarray, none: int, lo: int = 0, hi: int = 255) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    out = np.clip(np.rint(np.nan_to_num(x, nan=0.0)), lo, hi).astype(np.uint8)
    out[~np.isfinite(x)] = none
    return out


def _arr(b) -> np.ndarray:
    return np.asarray(b, dtype=np.float64)


WIND_MAX = 50.0
GUST_MAX = 60.0
RAIN_MAX = 64.0
CURRENT_MAX = 2.5


def encode_wind(ms):
    """Signed component, 128 = calm, +-127 steps = +-50 m/s."""
    return _bytes(128.0 + _arr(ms) * 127.0 / WIND_MAX, 128, 1, 255)


def decode_wind(b):
    return (_arr(b) - 128.0) * WIND_MAX / 127.0


def encode_gust(ms):
    return _bytes(_arr(ms) / GUST_MAX * 255.0, 0)


def decode_gust(b):
    return _arr(b) / 255.0 * GUST_MAX


def encode_rain(mmh):
    x = _arr(mmh)
    return _bytes(np.sqrt(np.clip(x, 0.0, RAIN_MAX) / RAIN_MAX) * 255.0, 0)


def decode_rain(b):
    return (_arr(b) / 255.0) ** 2 * RAIN_MAX


def encode_air_temp(c):
    return _bytes((_arr(c) + 60.0) / 110.0 * 255.0, 0)


def decode_air_temp(b):
    return _arr(b) / 255.0 * 110.0 - 60.0


def encode_sea_temp(c):
    return _bytes((_arr(c) + 2.0) / 36.0 * 255.0, 0)


def decode_sea_temp(b):
    return _arr(b) / 255.0 * 36.0 - 2.0


def encode_current(ms):
    return _bytes(128.0 + _arr(ms) / CURRENT_MAX * 127.0, 128, 1, 255)


def decode_current(b):
    return (_arr(b) - 128.0) / 127.0 * CURRENT_MAX


def encode_pressure(hpa):
    """1..255 = 940..1060 hPa; 0 = no value."""
    return _bytes(1.0 + (_arr(hpa) - 940.0) / 120.0 * 254.0, 0, 1, 255)


def decode_pressure(b):
    b = _arr(b)
    return np.where(b == 0, np.nan, 940.0 + (b - 1.0) / 254.0 * 120.0)


def encode_cloud(pct):
    """Provisional linear scale; Task 4 checks it against the reference."""
    return _bytes(_arr(pct) / 100.0 * 255.0, 0)


def decode_cloud(b):
    return _arr(b) / 255.0 * 100.0
