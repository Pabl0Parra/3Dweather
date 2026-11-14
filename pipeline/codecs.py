"""Byte encodings for the wave sprite: R = height, G/B = travel vector."""
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
